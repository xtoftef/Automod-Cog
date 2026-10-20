import discord
from discord.ext import commands
from discord import app_commands

from typing import cast, Literal, Optional
from collections import deque
import time
from datetime import timedelta
import discord


from src.memory_manager_implementations import JSONMemoryManager
from src.automod_engine import AutomodEngine
from src.automod_models import (
    BaseAutomodComponentConfig,BaseAutomodMemoryManager,
    AutomodLog,
    DeleteAction, MessageAction, TimeoutAction, DMAction, AutomodResponse
)
from src.automod_components.image_rate_limiter import ImageRateLimiterComponentConfig
from src.automod_components.chain_prevention import ChainPreventionComponentConfig
from DiscordUI.views import AutomodComponentConfigPanelView

# TODO: Note to self when i continue working on this. After some testing, i managed to solve quite a number of issues. Now the
# config panel is working. It feels like the architecture is nearly there, I might be able to just refactor the code now.
# Even the JSON memory is saving things properly
# To test properly with the image limiter: channel ignore, role ignore. Check if the bot properly reinitializes the automod when
# the config is updated. Okay so, i need to add the logic that restarts the automod with the new config.



CONFIG_REGISTRY: dict[
    str, type[BaseAutomodComponentConfig]
] = {
    ImageRateLimiterComponentConfig.CONFIG_KEY: ImageRateLimiterComponentConfig,
    ChainPreventionComponentConfig.CONFIG_KEY: ChainPreventionComponentConfig
}



DEFAULT_MEMORY = JSONMemoryManager("guild_data.json")


class AutomodCog(commands.Cog):
    "you can implement the commands and logic here, it also still supports the on_message function."

    def __init__(self, bot: commands.Bot, memory : BaseAutomodMemoryManager = DEFAULT_MEMORY ) -> None:
        super().__init__()
        self.bot = bot 
        self.automod_engine = AutomodEngine(memory, []) # NOTE: need to reset the list of guilds when the bot is ready.
        # you may modify the constructor if you see it needed
        

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        "Handles the messages that the bot receives."
        if not isinstance(message.author, discord.Member):
            return
        response = await self.automod_engine.engine_process_message(message)

        if response.flagged:
            await self._handle_automod_response(response, message)



    async def _handle_automod_response(self,response: AutomodResponse, message: discord.Message) -> list[str]:
        """Handles an automod response regarding a particular message.
        Each action runs independently, so one failing action (e.g. the user has DMs closed) doesn't stop the others.
        Returns a list describing the actions that failed (empty if all succeeded)."""
        failures: list[str] = []
        dm_action, delete_action, message_action, timeout_action = None , None, None , None

        for action in (response.actions or []):
            try:
                if action.action_type == 'delete':
                    action = cast(DeleteAction, action)
                    # 1. Delete the triggering message
                    await message.delete()

                    delete_action = action

                elif action.action_type == 'timeout':
                    action = cast(TimeoutAction, action)

                    exp_time = timedelta(minutes=action.duration)

                    if isinstance(message.author, discord.Member):
                        await message.author.timeout(exp_time,reason=action.reason)

                        timeout_action = action
                    

                elif action.action_type == 'message':
                    action = cast(MessageAction, action)
                    # 2. Send a temporary warning notice
                    warning = await message.channel.send(
                        action.formatted_message_response,
                        delete_after=5.0,  # Automatically cleans up warning notice after 5 seconds
                    )
                    message_action = action

                elif action.action_type == 'dm':
                    action = cast(DMAction, action)

                    await message.author.send(action.formatted_message_response)
                    dm_action = action

            except discord.NotFound:
                pass # Message or member is already gone (e.g. deleted by a moderator)
            except discord.HTTPException as e: # Includes Forbidden: missing permissions, DMs closed, member outranks the bot...
                failures.append(f"{action.action_type}: {e}")
                print(f"Automod action '{action.action_type}' failed in channel {message.channel.id}: {e}")


        log_channel = None

        if response.log_to and message.guild:
            log_channel = message.guild.get_channel(int(response.log_to))
            if not isinstance(log_channel, discord.TextChannel):
                log_channel = None

        log_data = AutomodLog(
            message_object= message,
            log_channel= log_channel,
            reason= response.reason,
            dm_success = ((True if dm_action else False), dm_action),
            message_success= ((True if message_action else False), message_action),
            timeout_success= ((True if timeout_action else False), timeout_action),
            delete_success= ((True if delete_action else False), delete_action)
        )

        await self._send_automod_log(log_data)

        return failures

    async def _send_automod_log(self, log_data: AutomodLog):
        "Sends a log in a specified channel"
        log_channel = log_data.log_channel
        if not log_channel:
            print("No log channel was set.")
            return 

        user = log_data.message_object.author
        message = log_data.message_object
        channel = message.channel
        
        if isinstance(channel, (discord.DMChannel, discord.GroupChannel)):
            raise Exception("DM or Group channel got somehow flagged? wth")

        has_attachments = True if message.attachments else False
        has_sticker = True if message.stickers else False

        extra_info = ""
        if has_attachments:
            extra_info += "Message has attachments\n"
        elif has_sticker:
            extra_info += "Message has stickers\n"

        delete_string = f"Message Deleted: {"✅" if log_data.delete_success[0] else "❌"}\n"
        dm_string = f"DM'd: {"✅" if log_data.dm_success[0] else "❌"}\n"
        verbal_message_string = f"Verbal Messaged: {"✅" if log_data.message_success[0] else "❌"}\n"
        timeout_string = f"Timedout: {f"✅ - Length: {log_data.timeout_success[1].duration}" if log_data.timeout_success[0] else "❌"}\n" #type: ignore

        log_string = (f"AUTOMOD LOG:\n"
                      f"Reason: {log_data.reason}\n"
                      f"User: <@{user.id}> - `{user.name}`\n"
                      f"In: {channel.mention}\n"
                      f"**Flagged Message:**\n> {message.content}\n"
                      f"{extra_info}"
                      f"{delete_string}{dm_string}{verbal_message_string}{timeout_string}")

        
        await log_channel.send(log_string)



    # ==============================================================================
    # AUTOCOMPLETES
    # ==============================================================================
    async def config_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocompletes choices based on registered configs matching current user input."""
        
        return [
            app_commands.Choice(name=key, value=key)
            for key in self.automod_engine.AVAILABLE_COMPONENTS
            if current.lower() in key.lower()
        ]

    async def existing_config_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocompletes only configs that exist for the current guild."""
        if not interaction.guild_id: return []

        guild_id = str(interaction.guild_id)
        existing_configs = await self.automod_engine.get_guild_components(guild_id)
        print("Existing conf:", existing_configs)

        return [
            app_commands.Choice(name=key, value=key)
            for key in existing_configs.keys()
            if current.lower() in key.lower()
        ]



    
    # ==============================================================================
    # COMMANDS
    # ==============================================================================
    @app_commands.command(
        name="config-view", description="View an existing automod config."
    )
    @app_commands.autocomplete(config_key=existing_config_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def view_config(self, interaction: discord.Interaction, config_key: str):
        guild_id = str(interaction.guild_id)
        if not guild_id: 
            return await interaction.response.send_message("This command can only be used inside of a guild.", ephemeral=True)
        guild_configs = await self.automod_engine.get_guild_configs(guild_id)#MOCK_CONFIG_STORE.get(guild_id, {})

        # Traverse through the list of config objects and retrieve the one matching the key
        cfg = next((config for config in guild_configs if config.CONFIG_KEY == config_key), None)#guild_configs[config_key]
        if not cfg: 
            return await interaction.response.send_message(
                f"❌ No active config found for `{config_key}` in this server.",
                ephemeral=True,
            )

        embed = discord.Embed(
            title=f"Configuration: {cfg.CONFIG_KEY}",
            color=discord.Color.blue(),
        )
        cfg_dict = cfg.to_dict()
        print(cfg_dict)
        for field_name, value in cfg_dict.items():
            embed.add_field(
                name=field_name.replace("_", " ").title(),
                value=f"`{value}`" if value != "" else "*None*",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


    @app_commands.command(
        name="config-update", description="Update an existing automod config."
    )
    @app_commands.autocomplete(config_key=existing_config_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def update_config(
        self, interaction: discord.Interaction, config_key: str
    ):
        
        guild_id = str(interaction.guild_id)
        if not guild_id or not interaction.guild: return await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
        guild_configs = await self.automod_engine.get_guild_configs(guild_id)#MOCK_CONFIG_STORE.get(guild_id, {})

        # Traverse through the list of config objects and retrieve the one matching the key
        cfg = next((config for config in guild_configs if config.CONFIG_KEY == config_key), None)#guild_configs[config_key]
        if not cfg: 
            return await interaction.response.send_message(
                f"❌ No config found for `{config_key}`. Use `/config-add` to create one first.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            view=AutomodComponentConfigPanelView(
                cfg, self.automod_engine, interaction.user.id, interaction.guild
            ),
            ephemeral=True,
        )


    @app_commands.command(
        name="config-add", description="Add a new automod configuration and edit it.",
    )
    @app_commands.autocomplete(config_key=config_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def add_config(self, interaction: discord.Interaction, config_key: str):
        if config_key not in CONFIG_REGISTRY:
            await interaction.response.send_message(
                f"❌ Invalid config type selected.", ephemeral=True
            )
            return


        guild_id = str(interaction.guild_id)
        if not guild_id or not interaction.guild: return await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
        guild_configs = await self.automod_engine.get_guild_configs(guild_id)
        
        # Traverse through the list of config objects and retrieve the one matching the key
        cfg = next((config for config in guild_configs if config.CONFIG_KEY == config_key), None)#guild_configs[config_key]
        if cfg: 
            return await interaction.response.send_message(
                f"❌ Existing config found for `{config_key}`. Use `/config-update` to update the config.",
                ephemeral=True,
            )

        ConfigClass= CONFIG_REGISTRY[config_key]

        # Initialize default config if not existing
        cfg = ConfigClass.get_default(guild_id)

        await interaction.response.send_message(
            view=AutomodComponentConfigPanelView(
                cfg, self.automod_engine, interaction.user.id, interaction.guild
            ),
            ephemeral=True,
        )



    
    # ==============================================================================
    # TEST COMMANDS
    # ==============================================================================
    @app_commands.command(
        name = "dummy-config-view",
        description="Purely for testing"
    )
    @app_commands.default_permissions(administrator=True)
    async def dummy_config(self, interaction:discord.Interaction):
        "Test command for a dummy."
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This test panel can only be opened inside a server.",
                ephemeral=True,
            )
            return

        dummy_config = ImageRateLimiterComponentConfig.get_default("Test") # This test guild_id won't work since the program will detect a guild_id mismatch.
        dummy_memory = JSONMemoryManager("dummy_memory.json")
        dummy_engine = AutomodEngine(dummy_memory, [guild])
    
        await interaction.response.send_message(
            view=AutomodComponentConfigPanelView(
                dummy_config, dummy_engine, interaction.user.id, guild
            ),
            ephemeral=True,
        )

    @app_commands.command(name= "test-automod")
    @app_commands.default_permissions(administrator=True) # Can delete messages and time out members, so admins only
    async def test_automod_action(self, 
        interaction: discord.Interaction, 
        msg_id: str, 
        action_type:Literal['delete', 'message', 'dm', 'timeout'], 
        log_channel_id : Optional[str] = None
        ):

        # Get message
        if not interaction.channel or isinstance(interaction.channel, (discord.ForumChannel,discord.CategoryChannel)): return

        msg = await interaction.channel.fetch_message(int(msg_id))

        automod = None
        match action_type:
            case 'delete':
                automod = AutomodResponse(False, "Test Delete", [DeleteAction()], log_channel_id)
            case 'dm':
                automod = AutomodResponse(False, "Test DM", [DMAction("Hi")], log_channel_id)
            case 'message':
                automod = AutomodResponse(False, "Test message", [MessageAction("Hi")], log_channel_id)
            case 'timeout':
                automod = AutomodResponse(False, "Test timeout", [TimeoutAction(60,"Mute test")], log_channel_id)

        if not automod: return

        try:
            failures = await self._handle_automod_response(automod, msg)
            if failures:
                await interaction.response.send_message(f"Automod action failed. Error: {'; '.join(failures)}", ephemeral=True)
            else:
                await interaction.response.send_message("Automod action successful", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Automod action failed. Error: {e}", ephemeral=True)
