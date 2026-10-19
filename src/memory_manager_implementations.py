import json
import os
from typing import Type, Any

from src.automod_models import (
    BaseAutomodMemoryManager,
    ConfigT,
    BaseAutomodComponentConfig
)
from src.automod_components.image_rate_limiter import ImageRateLimiterComponentConfig
from src.automod_components.chain_prevention import ChainPreventionComponentConfig


class JSONMemoryManager(BaseAutomodMemoryManager):

    CONFIG_MAP = {
        BaseAutomodComponentConfig.CONFIG_KEY : BaseAutomodComponentConfig,
        ImageRateLimiterComponentConfig.CONFIG_KEY : ImageRateLimiterComponentConfig,
        ChainPreventionComponentConfig.CONFIG_KEY : ChainPreventionComponentConfig
    }

    def __init__(self, memory_file_path: str) -> None:
        super().__init__()
        self.file_path = memory_file_path
        self.loaded_memory : dict[str, dict]
        self.load_memory()

    def load_memory(self):
        try:
            with open(self.file_path,"r") as f:
                loaded = json.load(f)
        except FileNotFoundError:
            self.loaded_memory = {}
            return

        if not isinstance(loaded, dict):
            raise ValueError(f"Memory file must contain a JSON object: {self.file_path}")
        self.loaded_memory = loaded

    def save_memory(self):
        # Write to a temporary file first, then swap it in. If the bot crashes mid-write,
        # the old file stays intact instead of being left half-written (which would stop the bot from starting).
        temp_path = self.file_path + ".tmp"
        try:
            with open(temp_path, "w") as f:
                json.dump(self.loaded_memory, f, indent=2)
            os.replace(temp_path, self.file_path)
        except OSError as e:
            print(f"Ran into an error while trying to save the JSON file. Passed path: {self.file_path}")
            raise e

    async def global_get_config(
        self,
        guild_id: str,
        config_type: Type[ConfigT],
    ) -> ConfigT:
        "Global method that acts as a router to get a specific config for a specific guild"
        if not isinstance(config_type, type) or not issubclass(
            config_type, BaseAutomodComponentConfig
        ):
            raise TypeError("config_type must be a BaseAutomodComponentConfig subclass")
        if not config_type.CONFIG_KEY:
            raise ValueError(f"{config_type.__name__} must define CONFIG_KEY")

        guild_configs = self.loaded_memory.get(guild_id, {})
        stored_config = guild_configs.get(config_type.CONFIG_KEY)
        if stored_config is None:
            config = config_type.get_default(guild_id)
            await self.global_set_config(config)
            return config
        if not isinstance(stored_config, dict):
            raise ValueError(
                f"Stored config {config_type.CONFIG_KEY!r} for guild {guild_id!r} "
                "must be a JSON object"
            )
        return config_type.from_dict(stored_config)

    async def global_set_config(self, config: BaseAutomodComponentConfig) -> None:
        if not isinstance(config, BaseAutomodComponentConfig):
            raise TypeError("config must be a BaseAutomodComponentConfig instance")
        if not config.CONFIG_KEY:
            raise ValueError(f"{type(config).__name__} must define CONFIG_KEY")

        self.loaded_memory.setdefault(config.guild_id, {})[config.CONFIG_KEY] = config.to_dict()
        self.save_memory()

    def sync_get_all_guild_configs(self, guild_id: str) -> list[BaseAutomodComponentConfig]:
    
        # TODO: Add error handling

        config_list: list[BaseAutomodComponentConfig] = []

        # Fetch the guild configs
        guild_configs = self.loaded_memory.get(guild_id, None)
        print("Loaded memory:", self.loaded_memory)
        if not guild_configs:
            print("No guild config found for ", guild_id)
            return []

        
        for config_key, data in guild_configs.items():
            try:
                config_type = self.CONFIG_MAP[config_key] # can throw an error if the memory got altered
                config_list.append(config_type.from_dict(data)) # from dict can throw an error
            except Exception as e:
                # Skip the broken entry instead of crashing, so one renamed/removed component or corrupted entry
                # doesn't stop every guild's automods from starting. The entry is kept in the file untouched.
                print(f"Skipping anomalous config. Key: {config_key}, Guild ID: {guild_id}, Error: {e!r}")

        return config_list

    async def get_all_guild_configs(self, guild_id: str) -> list[BaseAutomodComponentConfig]:
        return self.sync_get_all_guild_configs(guild_id)
        

    async def get_all_guild_data(self) -> dict[str, dict[str, BaseAutomodComponentConfig]]:
        guild_data  = {} 
        for guild_id in self.loaded_memory.keys():
            guild_data[guild_id] = await self.get_all_guild_configs(guild_id)

        return guild_data


        