import discord
from discord.ext import commands, tasks
from discord import app_commands

from typing import cast, Literal, Optional
from datetime import timedelta
import io
import discord


from src.memory_manager_implementations import JSONMemoryManager
from src.data_gathering.media_stats_models import BaseMediaStatsStorage
from src.data_gathering.media_stats_storage import JSONMediaStatsStorage
from src.data_gathering.media_stats_collector import MediaStatsCollector
from src.automod_engine import AutomodEngine
from src.automod_models import (
    BaseAutomodComponentConfig,BaseAutomodMemoryManager,
    AutomodLog,
    DeleteAction, MessageAction, TimeoutAction, DMAction, AutomodResponse
)
from DiscordUI.views import AutomodComponentConfigPanelView, MasterPanelView, AutomodLogView
from config import ENGINE_CONFIG, get_component_related_class
from logger import setup_automod_logging, get_logger

DEFAULT_MEMORY = JSONMemoryManager("guild_data.json") # not using the config.py one since it's just a 
# default that can be overriden when creating the cog object.
DEFAULT_MEDIA_STATS_STORAGE = JSONMediaStatsStorage("media_stats.json")


logger = get_logger("cog")

class AutomodCog(commands.Cog):
    "you can implement the commands and logic here, it also still supports the on_message function."

    def __init__(
        self,
        bot: commands.Bot,
        memory : BaseAutomodMemoryManager = DEFAULT_MEMORY,
        media_stats_storage : BaseMediaStatsStorage = DEFAULT_MEDIA_STATS_STORAGE
    ) -> None:
        logger.debug("Booting up automod cog")
        super().__init__()
        setup_automod_logging()
        self.bot = bot
        self.automod_engine = AutomodEngine(memory, []) # NOTE: need to reset the list of guilds when the bot is ready.
        self.media_stats = MediaStatsCollector(media_stats_storage) # data gathering, independent from the engine
        # you may modify the constructor if you see it needed

        logger.info("Automod Cog successfully initialized")

    async def cog_load(self) -> None:
        self.flush_media_stats.start()

    async def cog_unload(self) -> None:
        self.flush_media_stats.cancel()
        self.media_stats.flush()

    @tasks.loop(seconds=60)
    async def flush_media_stats(self):
        "Writes the gathered media stats to the storage periodically instead of on every message."
        self.media_stats.flush()


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        "Handles the messages that the bot receives."
        logger.info(f"Received message from {message.author.name}")
        if not isinstance(message.author, discord.Member):
            logger.debug(f"Ignoring message from member not found within a guild. User: {message.author.name}")
            return
        # Recorded before the automod runs, so messages the automod deletes are still counted
        self.media_stats.record_message(message)

        response = await self.automod_engine.engine_process_message(message)

        if response.flagged:
            logger.debug("Flagged an automod. Handling response.")
            await self._handle_automod_response(response, message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Link embeds (tenor gifs, image/video links) are usually added by Discord after the message was sent,
        through an edit. Only those late embeds are recorded, attachments were already counted in on_message."""
        if before.embeds or not after.embeds:
            return
        self.media_stats.record_message(after, attachments=False)



    async def _handle_automod_response(self,response: AutomodResponse, message: discord.Message) -> list[str]:
        """Handles an automod response regarding a particular message.
        Each action runs independently, so one failing action (e.g. the user has DMs closed) doesn't stop the others.
        Returns a list describing the actions that failed (empty if all succeeded)."""
        failures: list[str] = []
        dm_action, delete_action, message_action, timeout_action = None , None, None , None

        for action in (response.actions or []):
            logger.debug("Entering action loop")
            if not action.enabled:
                logger.debug(f"Action {action} ignored due to it being disabled")
                continue
            try:
                if action.action_type == 'delete':
                    logger.debug("Attempting delete action")
                    action = cast(DeleteAction, action)
                    # 1. Delete the triggering message
                    await message.delete()

                    delete_action = action

                elif action.action_type == 'timeout':
                    logger.debug(f"Attempting timeout action. User: {message.author.name}")
                    action = cast(TimeoutAction, action)

                    exp_time = timedelta(minutes=action.duration)

                    if isinstance(message.author, discord.Member):
                        await message.author.timeout(exp_time,reason=action.reason)

                        timeout_action = action
                    

                elif action.action_type == 'message':
                    DMchan = discord.DMChannel ; PartialMess = discord.PartialMessageable
                    logger.debug(f"Attempting channel message action. Channel: {message.channel.name if not isinstance(message.channel,(DMchan, PartialMess)) else "DM or Partial Messageable"}")
                    action = cast(MessageAction, action)
                    # 2. Send a temporary warning notice
                    await message.channel.send(
                        action.format_response(response.response_values),
                        delete_after=5.0,  # Automatically cleans up warning notice after 5 seconds
                    )
                    message_action = action

                elif action.action_type == 'dm':
                    logger.debug(f"Attempting to send DM to {message.author.name}")
                    action = cast(DMAction, action)

                    await message.author.send(
                        action.format_response(response.response_values)
                    )
                    dm_action = action

            except discord.NotFound:
                logger.exception("Not Found error")
                pass # Message or member is already gone (e.g. deleted by a moderator)
            except discord.HTTPException as e: # Includes Forbidden: missing permissions, DMs closed, member outranks the bot...
                logger.exception("Caught a Discord HTTP exception.")
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
        logger.debug(f"Created automod log dataclass: {log_data}")

        await self._send_automod_log(log_data)

        return failures

    async def _send_automod_log(self, log_data: AutomodLog):
        "Sends a log in a specified channel"
        logger.info("Attempting to send log to the set automod logging channel if any.")
        log_channel = log_data.log_channel
        if not log_channel:
            logger.debug("No logging channel was set.")
            print("No log channel was set.")
            return 

        message = log_data.message_object
        channel = message.channel
        
        if isinstance(channel, (discord.DMChannel, discord.GroupChannel)):
            logger.debug(f"Unexpected exception. Illegal channel was added maybe. {channel.type}")
            raise Exception("DM or Group channel got somehow flagged? wth")

        
        view = AutomodLogView(automod_log=log_data)

        allowed_mentions = discord.AllowedMentions(
            everyone=False, users=False
        )

        logger.debug("Attempting to send log to the channel.")
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
        logger.debug("Triggered config_autocomplete class")
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
        logger.debug(f"[existing_config_autocomplete] Existing conf: {existing_configs}")

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
        logger.info("Attempting `open-master-panel` command.")
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
        logger.info("attempting `view_config` command.")
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
            await interaction.edit_original_response(
                content=f"❌ Invalid config type selected."
            )
            return


        guild_id = str(interaction.guild_id)
        if not guild_id or not interaction.guild: return await interaction.edit_original_response(content="This command can only be used in a guild")
        guild_configs = await self.automod_engine.get_guild_configs(guild_id)
        
        # Traverse through the list of config objects and retrieve the one matching the key
        cfg = next((config for config in guild_configs if config.COMPONENT_KEY == config_key), None)#guild_configs[config_key]
        if cfg: 
            return await interaction.edit_original_response(
                content=f"❌ Existing config found for `{config_key}`. Use `/config-update` to update the config."
            )


        ConfigClass = get_component_related_class(config_key, 'config_type')

        # Initialize default config if not existing
        if not issubclass(ConfigClass, BaseAutomodComponentConfig): raise TypeError(f"Meant to retrieve Config subclass but retrieved {type(ConfigClass)} instead")
        
        cfg = ConfigClass.get_default(guild_id)

        await interaction.edit_original_response(
            view=AutomodComponentConfigPanelView(
                cfg, self.automod_engine, interaction.user.id, interaction.guild
            )
        )



    
    # ==============================================================================
    # DATA GATHERING COMMANDS
    # ==============================================================================
    @app_commands.command(
        name="media-stats-watch", description="Gather media stats (gifs, images, videos per user per day) in a channel."
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only
    async def media_stats_watch(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        days: app_commands.Range[int, 1, 90] = 7
    ):
        logger.info("Attempting `media-stats-watch` command.")
        if not interaction.guild_id: return
        session = self.media_stats.watch_channel(str(interaction.guild_id), str(channel.id), days)
        await interaction.response.send_message(
            f"📊 Gathering media stats in {channel.mention} until <t:{int(session.ends_at)}:F>.\n"
            "-# Watching a channel again restarts the period, the stats gathered so far are kept.",
            ephemeral=True,
        )

    @app_commands.command(
        name="media-stats-unwatch", description="Stop gathering media stats in a channel."
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only
    async def media_stats_unwatch(self, interaction: discord.Interaction, channel: discord.TextChannel):
        logger.info("Attempting `media-stats-unwatch` command.")
        self.media_stats.flush()
        if self.media_stats.unwatch_channel(str(channel.id)):
            await interaction.response.send_message(f"⏹️ Stopped gathering media stats in {channel.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {channel.mention} is not being watched.", ephemeral=True)

    @app_commands.command(
        name="media-stats-view", description="View the daily media stats gathered in a channel."
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only
    async def media_stats_view(self, interaction: discord.Interaction, channel: discord.TextChannel):
        logger.info("Attempting `media-stats-view` command.")
        session = self.media_stats.watches.get(str(channel.id))
        if not session or session.guild_id != str(interaction.guild_id):
            return await interaction.response.send_message(f"❌ No stats were gathered in {channel.mention}.", ephemeral=True)

        is_active = self.media_stats.get_active_session(str(channel.id)) is not None
        embed = discord.Embed(
            title=f"Media stats: #{channel.name}",
            description=(f"**Status:** 🟢 Watching, ends <t:{int(session.ends_at)}:R>" if is_active
                         else f"**Status:** ⚪ Ended <t:{int(session.ends_at)}:R>"),
            color=discord.Color.blue(),
        )
        summaries = self.media_stats.summarize_channel(str(channel.id))
        for summary in summaries[:10]: # embeds are limited to 25 fields, last 10 days is plenty
            embed.add_field(
                name=summary.day,
                value=(f"Users sending media: `{summary.users}`\n"
                       f"Gif: `{summary.totals.gif}` | Image: `{summary.totals.image}` | Video: `{summary.totals.video}`\n"
                       f"Per user - avg: `{summary.average_per_user:.1f}`, median: `{summary.median_per_user:g}`, max: `{summary.max_per_user}`"),
                inline=False,
            )
        if not summaries:
            embed.add_field(name="No data yet", value="No media was sent in the channel since it started being watched.")
        elif len(summaries) > 10:
            embed.set_footer(text=f"Showing the last 10 of {len(summaries)} days. Use /media-stats-export for everything.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="media-stats-export", description="Export the gathered media stats of this server as a CSV file."
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only
    async def media_stats_export(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        logger.info("Attempting `media-stats-export` command.")
        guild_id = str(interaction.guild_id)
        channel_ids = [session.channel_id for session in self.media_stats.get_guild_sessions(guild_id)]
        if channel:
            channel_ids = [channel_id for channel_id in channel_ids if channel_id == str(channel.id)]
        if not channel_ids:
            return await interaction.response.send_message("❌ No stats were gathered for this selection.", ephemeral=True)

        csv_string = self.media_stats.export_csv(channel_ids)
        await interaction.response.send_message(
            file=discord.File(io.BytesIO(csv_string.encode("utf-8")), filename=f"media_stats_{guild_id}.csv"),
            ephemeral=True,
        )


    # ==============================================================================
    # TEST COMMANDS
    # ==============================================================================
    @app_commands.command(name= 'ping')
    async def ping(self, interaction: discord.Interaction):
        "Returns the bot's ping"
        await interaction.response.send_message(f"Pong: **{round(self.bot.latency * 1000)} ms**")


    @app_commands.command(name="stats")
    async def stats(self, interaction: discord.Interaction):
        import psutil
        import os
        await interaction.response.defer()
        # 1. Calculate Ping (latency in ms)
        latency = round(self.bot.latency * 1000)

        # 2. Get Process Resource Usage (CPU & RAM for this bot process)
        process = psutil.Process(os.getpid())
        cpu_usage = process.cpu_percent(interval=None)
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024  # Convert bytes to MB

        # 3. Get System-wide RAM Usage (optional summary)
        virtual_mem = psutil.virtual_memory()

        # 4. Build and send an embed
        embed = discord.Embed(title="Bot Status & Resource Usage", color=0x3498DB)
        embed.add_field(name="Ping", value=f"{latency} ms", inline=True)
        embed.add_field(name="CPU Usage", value=f"{cpu_usage}%", inline=True)
        embed.add_field(
            name="Memory (RAM)",
            value=f"{memory_mb:.2f} MB ({virtual_mem.percent}% system used)",
            inline=False,
        )

        await interaction.edit_original_response(embed=embed)

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
