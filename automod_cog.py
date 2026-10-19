import discord
from discord.ext import commands
from discord import app_commands

from typing import cast, Literal
from collections import deque
import time
from datetime  import datetime, timedelta
import discord

from src.memory_manager_implementations import JSONMemoryManager
from src.automod_engine import AutomodEngine
from src.component_implementations import BaseAutomodMemoryManager, BaseAutomodComponentConfig, ImageRateLimiterComponentConfig
from DiscordUI.views import AutomodComponentConfigPanelView
from src.automod_models import (
    DeleteAction, MessageAction, TimeoutAction, DMAction, AutomodResponse
)

# TODO: Note to self when i continue working on this. After some testing, i managed to solve quite a number of issues. Now the
# config panel is working. It feels like the architecture is nearly there, I might be able to just refactor the code now.
# Even the JSON memory is saving things properly
# To test properly with the image limiter: channel ignore, role ignore. Check if the bot properly reinitializes the automod when
# the config is updated. Okay so, i need to add the logic that restarts the automod with the new config.



CONFIG_REGISTRY: dict[
    str, type[BaseAutomodComponentConfig]
] = {
    ImageRateLimiterComponentConfig.CONFIG_KEY: ImageRateLimiterComponentConfig
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
            

    async def _handle_automod_response(self,response: AutomodResponse, message: discord.Message):
        "Handles an automod response regarding a particular message"
        for action in (response.actions or []):
            if action.action_type == 'delete':
                action = cast(DeleteAction, action)
                # 1. Delete the triggering message
                await message.delete()
            elif action.action_type == 'timeout':
                action = cast(TimeoutAction, action)
                    
                exp_time = timedelta(minutes=action.duration)

                if isinstance(message.author, discord.Member):
                    await message.author.timeout(exp_time,reason=action.reason) 

            elif action.action_type == 'message':
                action = cast(MessageAction, action)
                # 2. Send a temporary warning notice
                warning = await message.channel.send(
                    action.formatted_message_response,
                    delete_after=5.0,  # Automatically cleans up warning notice after 5 seconds
                )
            elif action.action_type == 'dm':
                action = cast(DMAction, action)

                await message.author.send(action.formatted_message_response)

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
    async def test_automod_action(self, interaction: discord.Interaction, msg_id: str, action_type:Literal['delete', 'message', 'dm', 'timeout']):

        # Get message
        if not interaction.channel or isinstance(interaction.channel, (discord.ForumChannel,discord.CategoryChannel)): return

        msg = await interaction.channel.fetch_message(int(msg_id))

        automod = None
        match action_type:
            case 'delete':
                automod = AutomodResponse(False, "", [DeleteAction()])
            case 'dm':
                automod = AutomodResponse(False, "", [DMAction("Hi")])
            case 'message':
                automod = AutomodResponse(False, "", [MessageAction("Hi")])
            case 'timeout':
                automod = AutomodResponse(False, "", [TimeoutAction(60,"Mute test")])

        if not automod: return

        try:
            await self._handle_automod_response(automod, msg)
            await interaction.response.send_message("Automod action successful")
        except Exception as e:
            await interaction.response.send_message(f"Automod action failed. Error: {e}")

