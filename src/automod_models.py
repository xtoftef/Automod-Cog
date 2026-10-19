from __future__ import annotations

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import ClassVar, TypeVar, Generic, Type, Self, Any, Literal, LiteralString

from discord.abc import GuildChannel
from discord import Guild, Message, Member
from discord.channel import (
    TextChannel,StageChannel, VoiceChannel, ForumChannel, CategoryChannel
)

from utils import OrderedSet

VALID_AUTOMOD_CHANNELS = (TextChannel, StageChannel, VoiceChannel)

GUILD_CHANNELS = (VoiceChannel, StageChannel, ForumChannel, CategoryChannel, TextChannel)

@dataclass
class AutomodResponse:
    "Response returned to the Discord bot"
    flagged : bool # True if the message flagged the automod, False if not
    reason : str
    actions : list[BotAction] | None # Actions that the bot should perform regarding the flagged message/user
    

@dataclass
class BotAction:
      # Should be a string literal
    @property
    @abstractmethod
    def action_type(self) -> Literal['delete', 'timeout', 'dm', 'message']:
        pass


@dataclass
class DeleteAction(BotAction):
    @property
    def action_type(self): return 'delete'
    


@dataclass
class TimeoutAction(BotAction):
    """Sets a member's timeout
    Parameters:
        duration (int) : Time in minutes for how long the timeout lasts
        reason (str) : The reason shown in the audit log
    """
    duration: int
    reason: str

    @property
    def action_type(self): return 'timeout'


@dataclass
class DMAction(BotAction):
    formatted_message_response: str

    @property
    def action_type(self): return 'dm'


@dataclass
class MessageAction(BotAction):
    """Sends a message in the channel triggered"""
    formatted_message_response: str

    @property
    def action_type(self): return 'message'

@dataclass
class BaseAutomodComponentConfig(ABC):
    CONFIG_KEY: ClassVar[str] = ""
    RESPONSE_PLACEHOLDERS: ClassVar[tuple[str, ...]] = ("user_id",) # placeholders usable in message_response_template
    guild_id : str # guild for which the config belongs
    is_global : bool # whether or not the automod affects all the channels of a guild
    affected_channels : OrderedSet # can include categories
    ignored_channels : OrderedSet # Does nothing if is_global is False
    ignored_roles : OrderedSet # roles unaffected by the automod
    message_response_template : str # Template that will be formatted whenever the bot will post it

    @classmethod
    @abstractmethod
    def get_default(cls, guild_id: str) -> Self:
        "Returns a default instance of the dataclass"

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        "Formats the dataclass into a dictionary"

    @classmethod
    @abstractmethod
    def from_dict(cls, config_dict: dict) -> Self:
        "Attempts to format the dictionary into the dataclass. Raises ValueError if the dictionary passed is not in the right format."

    @abstractmethod
    def format_response(self, user_id: str) -> str:
        "Formats the string into a response ready to be sent by the bot"   

    @abstractmethod
    def format_unique_config_display(self) -> str:
        """Intended to format a string with the UNIQUE attributes of the component. DO NOT INCLUDE GENERAL/SHARED ATTRIBUTES.
        \nExample:\n
        f"**Max Images:** `{config.max_images}`\\n"\n
        f"**Window Size:** `{config.window_size}` messages\\n"\n
        f"**Duration:** `{config.duration}` seconds\""""
        

ConfigT = TypeVar("ConfigT", bound=BaseAutomodComponentConfig)

class BaseChannelManager(ABC):
    "Individual channel instance of an automod."
    def __init__(self, channel_id: str, config: BaseAutomodComponentConfig) -> None:
        super().__init__()
        self.channel_id = channel_id
        self.config = config

ManagerT = TypeVar("ManagerT", bound=BaseChannelManager)

class BaseAutomodMemoryManager(ABC):
    "Base class for the memory management"
    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    async def global_get_config(
        self,
        guild_id: str,
        config_type: Type[ConfigT],
    ) -> ConfigT:
        "Loads the guild's config of the requested config subclass."

    @abstractmethod
    async def global_set_config(self, config: BaseAutomodComponentConfig) -> None:
        "Persists an instance of a config subclass."

    @abstractmethod
    def sync_get_all_guild_configs(self, guild_id: str) -> list[BaseAutomodComponentConfig]:
        "Non-async version of the command to make it possible upon initialization. Fetches all the config settings of a given guild"

    @abstractmethod
    async def get_all_guild_configs(self, guild_id: str) -> list[BaseAutomodComponentConfig]:
        "Fetches all the config settings of a given guild"

    @abstractmethod
    async def get_all_guild_data(self) -> dict[str, dict[str, BaseAutomodComponentConfig]]:
        "Fetches all the data found for all guilds. Usually used upon initialization"

# NOTE: Both type parameters preserve each component's concrete manager and config types.
class BaseAutomodComponent(ABC, Generic[ManagerT, ConfigT]):
    "Base class from which all automod components will inherit"

    CONFIG_KEY: ClassVar[str] = ""

    def __init__(
        self,
        config: ConfigT,
        guild: Guild,
        memory: BaseAutomodMemoryManager,
    ) -> None:
        super().__init__()
        self.config = config
        self.memory = memory
        self.channels: dict[str, ManagerT] = {}
        self.initialize_channel_helpers(guild)
        if not self._config_key_matches():
            raise NotImplementedError((f"Config Key mismatch detected.\nComponent key: {self.CONFIG_KEY}"
                                       f"\nPassed Config key: {self.config.CONFIG_KEY}\nMake sure you implemented the automod component properly."))

    def _config_key_matches(self) -> bool:
        "Method used to check if the config key of the automod component matches that of the config"
        return self.CONFIG_KEY == self.config.CONFIG_KEY

    def is_channel_watched(self, channel: GuildChannel) -> bool:
        "Checks if the config covers a channel. A channel is also covered when its category is selected."
        if not isinstance(channel, VALID_AUTOMOD_CHANNELS):
            return False
        channel_ids = {str(channel.id)}
        if channel.category_id is not None:
            channel_ids.add(str(channel.category_id))
        if self.config.is_global:
            return not (channel_ids & set(self.config.ignored_channels))
        return bool(channel_ids & set(self.config.affected_channels))


    def initialize_channel_helpers(self, guild:Guild):
        "Synchronizes managers with the guild's eligible channels."
        for channel in guild.channels:
            if self.is_channel_watched(channel):
                self.add_manager(str(channel.id))

    async def update_config(self, new_config: ConfigT, guild: Guild) -> None:
        "Updates the config and refreshes the channel managers. Takes a guild parameter to get the latest setup of a guild"
        if new_config.guild_id != str(guild.id):
            raise ValueError("The config guild_id must match the provided guild.")
        await self.memory.global_set_config(new_config)
        self.config = new_config
        self.channels = {} # clear the runtime memory
        self.initialize_channel_helpers(guild)

    def get_manager(self, channel_id: str) -> ManagerT | None:
        "Fetches and returns the manager assigned to a channel. Returns None if not found"
        return self.channels.get(channel_id, None)

    def remove_manager(self, channel_id: str) -> ManagerT | None:
        "Removes a channel from being watched."
        return self.channels.pop(channel_id, None)

    def check_for_immunity(self, user: Member) -> bool:
        "Checks if the user is immune"
        user_roles = [str(role.id) for role in user.roles]

        for role in self.config.ignored_roles:
            if role in user_roles:
                return True
        return False

    async def process_message(self, guild: Guild, channel: GuildChannel, message: Message) -> AutomodResponse:
        "Runs shared validity checks before dispatching to the component-specific handler."
        if str(channel.guild.id) != str(guild.id):
            return AutomodResponse(False, "Channel does not belong to the provided guild", None)

        channel_manager = self.get_manager(str(channel.id))
        if channel_manager is None and self.is_channel_watched(channel):
            # Channel was created (or moved into a watched category) after the managers were initialized
            self.add_manager(str(channel.id))
            channel_manager = self.get_manager(str(channel.id))

        if channel_manager is None:
            return AutomodResponse(False, "Channel is not watched", None)

        user = message.author
        if not isinstance(user, Member):
            return AutomodResponse(False, "Message was not sent in a guild...", None)

        is_immune = self.check_for_immunity(user)

        return await self._process_valid_message(channel_manager, user, message, is_immune)

    @abstractmethod
    def add_manager(self, channel_id: str):
        "Adds a manager to the self.channels attribute" 

    @abstractmethod
    async def _process_valid_message(
        self,
        channel_manager: ManagerT,
        user: Member,
        message: Message,
        is_immune: bool
    ) -> AutomodResponse:
        "Processes a message after shared channel and guild-member checks pass."


    @classmethod
    def from_config(
        cls,
        config: BaseAutomodComponentConfig,
        memory: BaseAutomodMemoryManager,
        guild: Guild,
    ) -> BaseAutomodComponent:
        "Convenience method to route/create a config based on what has been implemented"
        from src.automod_components.image_rate_limiter import ImageRateLimiterComponentConfig, ImageRateLimiterComponent
        from src.automod_components.chain_prevention import ChainPreventionComponentConfig, ChainPreventionComponent

        if isinstance(config, ImageRateLimiterComponentConfig):
            return ImageRateLimiterComponent(guild, memory, config)
        elif isinstance(config, ChainPreventionComponentConfig):
            return ChainPreventionComponent(guild, memory, config)

        # TODO: Add more components to the if-elif ladders

        raise TypeError(f"Unsupported config type: {type(config).__name__}")
        from src.component_implementations import from_config # Former code, might keep it there in case i want to bring it back up under a new version
        return from_config(config, memory, guild)
