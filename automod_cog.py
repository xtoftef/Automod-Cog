import discord
from discord.ext import commands
from discord import app_commands

from typing import cast, Literal, Optional
from datetime import timedelta
import discord


from src.memory_manager_implementations import JSONMemoryManager
from src.automod_engine import AutomodEngine
from src.automod_models import (
    BaseAutomodComponentConfig,BaseAutomodMemoryManager,
    AutomodLog,
    DeleteAction, MessageAction, TimeoutAction, DMAction, AutomodResponse
)
from DiscordUI.views import AutomodComponentConfigPanelView, MasterPanelView, AutomodLogView
from config import ENGINE_CONFIG, get_component_related_class


DEFAULT_MEMORY = JSONMemoryManager("guild_data.json") # not using the config.py one since it's just a 
# default that can be overriden when creating the cog object.


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

        message = log_data.message_object
        channel = message.channel
        
        if isinstance(channel, (discord.DMChannel, discord.GroupChannel)):
            raise Exception("DM or Group channel got somehow flagged? wth")

        view = AutomodLogView(automod_log=log_data)

        allowed_mentions = discord.AllowedMentions(
            everyone=False, users=False
        )
        
        await log_channel.send(
            view=view, 
            allowed_mentions= allowed_mentions
        )



    # ==============================================================================
    # AUTOCOMPLETES
    # ==============================================================================
    async def config_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocompletes choices based on registered configs matching current user input."""
        engine_components = ENGINE_CONFIG['components']
        keys = [key for key in engine_components if engine_components[key]['activate']]
        
        return [
            app_commands.Choice(name=key, value=key)
            for key in keys
            if current.lower() in key.lower()
        ]

    async def existing_config_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocompletes only configs that exist for the current guild."""
        engine_components = ENGINE_CONFIG['components']
        if not interaction.guild_id: return []

        guild_id = str(interaction.guild_id)
        existing_configs = await self.automod_engine.get_guild_components(guild_id)
        #print("Existing conf:", existing_configs)

        return [
            app_commands.Choice(name=key, value=key)
            for key in existing_configs.keys()
            if ((current.lower() in key.lower()) and engine_components[key]["activate"])
        ]



    
    # ==============================================================================
    # COMMANDS
    # ==============================================================================
    @app_commands.command(
        name="open-master-panel", description="Master control panel to modify the server's automods"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only
    async def open_master_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        if not guild_id or not interaction.guild: return await interaction.edit_original_response(content="This command can only be used in a guild")
        
        guild_configs = await self.automod_engine.get_guild_configs(guild_id)

        await interaction.edit_original_response(
            view=MasterPanelView(
                self.automod_engine, guild_configs, interaction.user.id, interaction.guild, interaction
            ),
            
        )

    @app_commands.command(
        name="config-view", description="View an existing automod config."
    )
    @app_commands.autocomplete(config_key=existing_config_autocomplete)
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only
    async def view_config(self, interaction: discord.Interaction, config_key: str):
        guild_id = str(interaction.guild_id)
        await interaction.response.defer(ephemeral=True)
        if not guild_id: 
            return await interaction.edit_original_response(content="This command can only be used inside of a guild.")
        guild_configs = await self.automod_engine.get_guild_configs(guild_id)#MOCK_CONFIG_STORE.get(guild_id, {})

        # Traverse through the list of config objects and retrieve the one matching the key
        cfg = next((config for config in guild_configs if config.COMPONENT_KEY == config_key), None)#guild_configs[config_key]
        if not cfg: 
            return await interaction.edit_original_response(
                content=f"❌ No active config found for `{config_key}` in this server."
            )

        embed = discord.Embed(
            title=f"Configuration: {cfg.COMPONENT_KEY}",
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

        await interaction.edit_original_response(embed=embed)


    @app_commands.command(
        name="config-update", description="Update an existing automod config."
    )
    @app_commands.autocomplete(config_key=existing_config_autocomplete)
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only
    async def update_config(
        self, interaction: discord.Interaction, config_key: str
    ):
        
        guild_id = str(interaction.guild_id)
        if not guild_id or not interaction.guild: return await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
        guild_configs = await self.automod_engine.get_guild_configs(guild_id)#MOCK_CONFIG_STORE.get(guild_id, {})

        # Traverse through the list of config objects and retrieve the one matching the key
        cfg = next((config for config in guild_configs if config.COMPONENT_KEY == config_key), None)#guild_configs[config_key]
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
    @app_commands.guild_only
    async def add_config(self, interaction: discord.Interaction, config_key: str):
        await interaction.response.defer(ephemeral=True)
        engine_components = [key for key in ENGINE_CONFIG["components"] if ENGINE_CONFIG["components"][key]["activate"]]
        if config_key not in engine_components:
            await interaction.response.edit_message(
                content=f"❌ Invalid config type selected."
            )
            return


        guild_id = str(interaction.guild_id)
        if not guild_id or not interaction.guild: return await interaction.response.edit_message(content="This command can only be used in a guild")
        guild_configs = await self.automod_engine.get_guild_configs(guild_id)
        
        # Traverse through the list of config objects and retrieve the one matching the key
        cfg = next((config for config in guild_configs if config.COMPONENT_KEY == config_key), None)#guild_configs[config_key]
        if cfg: 
            return await interaction.response.edit_message(
                content=f"❌ Existing config found for `{config_key}`. Use `/config-update` to update the config."
            )


        ConfigClass = get_component_related_class(config_key, 'config_type')

        # Initialize default config if not existing
        if not issubclass(ConfigClass, BaseAutomodComponentConfig): raise TypeError(f"Meant to retrieve Config subclass but retrieved {type(ConfigClass)} instead")
        
        cfg = ConfigClass.get_default(guild_id)

        await interaction.response.edit_message(
            view=AutomodComponentConfigPanelView(
                cfg, self.automod_engine, interaction.user.id, interaction.guild
            )
        )



    
    # ==============================================================================
    # TEST COMMANDS
    # ==============================================================================
    @app_commands.command(name= 'check-engine-cache')
    @app_commands.default_permissions(administrator=True)
    async def check_engine_cache(self, interaction: discord.Interaction):
        # TODO: either handle large cache cases or disable the command outside of testing 
        import json
        await interaction.response.defer(ephemeral=True)

        print_cache : dict[str, list[str]]= {}
        for key, comp_list in self.automod_engine.cache.items():
            print_cache[key] = [ comp.__str__() for comp in comp_list]


        cache_string = f"Engine Cache:\n{json.dumps(print_cache)}"

        return await interaction.edit_original_response(
            content= cache_string
        )

    @app_commands.command(name= 'check-automod-cache')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only
    async def check_guild_component_cache(self, interaction: discord.Interaction):
        # TODO: either handle large cache cases or disable the command outside of testing 
        import json
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild_id 
        if not guild_id: return 

        comps = await self.automod_engine.get_guild_components(str(guild_id))
        print_cache = {}
        for key, component in comps.items():
            
            print_cache[key] = [chann_id for chann_id in component.channels]


        cache_string = f"Component Caches:\n{json.dumps(print_cache)}"

        return await interaction.edit_original_response(
            content= cache_string,
        )

    @app_commands.command(
        name = "dummy-config-view",
        description="Purely for testing"
    )
    @app_commands.default_permissions(administrator=True)
    async def dummy_config(self, interaction:discord.Interaction):
        "Test command for a dummy."
        # NOTE: emptied since it's not really used now, and used to cause an unnecessary import.


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
