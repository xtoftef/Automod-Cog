from discord import Guild, Message
import discord


from src.automod_models import (
    BaseAutomodComponentConfig,
    AutomodResponse,
    BaseAutomodMemoryManager, 
    BaseAutomodComponent,
)

from src.automod_components.image_rate_limiter import ImageRateLimiterComponent
from src.automod_components.reply_chain_prevention import ReplyChainPreventionComponent



class AutomodEngine():

    "Manager of all the automod components for all guilds"
    def __init__(self, memory:BaseAutomodMemoryManager, guilds: list[Guild]) -> None:
        self.memory = memory
        self.guilds = guilds
        print("Guilds:", guilds)
        self.cache : dict[str, dict[str,BaseAutomodComponent]] = {
            # guild_id -> dict of components (Config_key -> component object)
        }
        self.init_all_guilds_automod()
        

    def init_all_guilds_automod(self):
        "Activates the automods of all guilds"

        for guild in self.guilds:

            list_configs = self.memory.sync_get_all_guild_configs(str(guild.id))
            print(f"Config list for {guild.id}: {list_configs}")

            for component in [BaseAutomodComponent.from_config(config, self.memory, guild) for config in list_configs]:
                if str(guild.id) not in self.cache:
                    self.cache[str(guild.id)] = {}
                
                self.cache[str(guild.id)][component.COMPONENT_KEY] = component

    async def enable_component(self, guild: Guild, comp_key: str):
        "Enables the component for that guild"
        from config import ENGINE_CONFIG

        guild_id = str(guild.id)

        if comp_key not in ENGINE_CONFIG["components"]:
            raise KeyError(f"Invalid component key passed: {comp_key}")

        # 1. Retrieve the component
        try:
            guild_components = self.cache[guild_id]
            component  = guild_components[comp_key]
        except KeyError as e:
            return False # component not found, not enabled

        # 2. Check if disabled
        cfg : BaseAutomodComponentConfig = component.config
        if cfg.enabled:
            return False #component already enabled
        
        cfg.enabled = True
        # 3. Update the config + initialize
        await component.update_config(cfg, guild)

        return True

    async def disable_component(self, guild: Guild, comp_key: str):
        "Disables the component for that guild"
        from config import ENGINE_CONFIG

        guild_id = str(guild.id)

        if comp_key not in ENGINE_CONFIG["components"]:
            raise KeyError(f"Invalid component key passed: {comp_key}")

        # 1. Retrieve the component
        try:
            guild_components = self.cache[guild_id]
            component  = guild_components[comp_key]
        except KeyError as e:
            return False # component not found, disabled kinda

        # 2. Check if enabled
        cfg : BaseAutomodComponentConfig = component.config
        if not cfg.enabled:
            return False #component already disabled
        
        cfg.enabled = False
        # 3. Update the config + initialize
        await component.update_config(cfg, guild)

        return True

    async def engine_process_message(self, message:Message) -> AutomodResponse:
        """Functions as a routing to the different components. The engine routes to the respective set of automods assigned to a guild.
        Then the automods themselves route according to channel.
        Returns the first positive flag response"""

        guild = message.guild
        if not guild: return AutomodResponse(False, "Message was not received from guild", None, None)
        if not isinstance(message.channel, discord.abc.GuildChannel): return AutomodResponse(False, "Invalid channel", None, None)

        automod_component_dict = self.cache.get(str(guild.id), None)
        if not automod_component_dict: return AutomodResponse(False, "Guild has no automod component running...", None, None)


        for _, component in automod_component_dict.items():
            response = await component.process_message(guild, message.channel, message)
            if response.flagged:
                return response

        return AutomodResponse(False, "No automod component was triggered", None, None)


    async def get_guild_components(self, guild_id: str) -> dict[str,BaseAutomodComponent]:
        "Returns a list of components for that guild"
        guild_components = self.cache.get(guild_id, {})
        
        return guild_components

    async def get_guild_configs(self, guild_id: str) -> list[BaseAutomodComponentConfig]:
        "Returns a list of configs for that guild."
        return [component.config for _, component in (await self.get_guild_components(guild_id)).items()]

    async def get_single_config(self, guild_id: str, component_key: str) -> BaseAutomodComponentConfig | None:
        "Retrieves a guild's config"
        from config import get_component_related_class
        ConfigType = get_component_related_class(component_key, 'config_type')
        if not issubclass(ConfigType, BaseAutomodComponentConfig): return None

        config = await self.memory.global_get_config(guild_id, ConfigType)
        return config

    async def set_config(self, guild: Guild, config: BaseAutomodComponentConfig) -> bool:
        "Updates a given config for a given guild. Adds it for the first time if not existing."
        try:
            # Check if guild ids match
            if not (str(guild.id) == config.guild_id):
                raise ValueError("Passed guild object does not match config guild id")

            # Try to update the memory first
            await self.memory.global_set_config(config)

            # Try to create the component instance
            component = BaseAutomodComponent.from_config(config, self.memory, guild)

            # Then try to set the cache
            self.cache.setdefault(config.guild_id, {})[component.COMPONENT_KEY] = component

            return True
        except Exception as e:
            print(f"Ran into an unexpected exception: {e}")
            return False


