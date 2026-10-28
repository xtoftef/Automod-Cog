from __future__ import annotations

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import ClassVar, TypeVar, Generic, Type, Self, Any, Literal

from discord.abc import GuildChannel
from discord import Guild, Message, Member
from discord.channel import (
    TextChannel,StageChannel, VoiceChannel, ForumChannel, CategoryChannel
)

from utils import OrderedSet, safe_format

VALID_AUTOMOD_CHANNELS = (TextChannel, StageChannel, VoiceChannel)

GUILD_CHANNELS = (VoiceChannel, StageChannel, ForumChannel, CategoryChannel, TextChannel)

@dataclass
class AutomodResponse:
    "Response returned to the Discord bot"
    flagged : bool # True if the message flagged the automod, False if not
    reason : str
    actions : list[BotAction] | None # Actions that the bot should perform regarding the flagged message/user
    log_to : str | None # Channel ID
    response_values: dict[str, str | int | float] = field(default_factory=dict)
    
@dataclass
class AutomodLog:
    "Wrapper for the data shown in a log"
    message_object : Message
    log_channel : TextChannel | None
    reason: str
    dm_success : tuple[bool, DMAction | None]
    message_success :  tuple[bool, MessageAction | None]
    timeout_success : tuple[bool, TimeoutAction | None]
    delete_success : tuple[bool, DeleteAction | None]

@dataclass
class BotAction:
    enabled: bool = field(default=True, kw_only=True)

    @property
    @abstractmethod
    def action_type(self) -> Literal['delete', 'timeout', 'dm', 'message']:
        pass

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize this action config for JSON storage."""

    @classmethod
    def from_dict(cls, action_dict: dict[str, Any]) -> BotAction:
        """Deserialize an action config using its action_type discriminator."""
        if not isinstance(action_dict, dict):
            raise ValueError("BotAction.from_dict expects a dictionary.")
        action_type = action_dict.get("action_type")
        if not isinstance(action_type, str):
            raise ValueError("Action dictionary must include a string 'action_type'.")
        action_class = BOT_ACTION_TYPES.get(action_type)
        if action_class is None:
            raise ValueError(f"Unknown automod action type: {action_type!r}")
        return action_class.from_dict(action_dict)

    @classmethod
    def list_from_dict(cls, actions_data: Any) -> list[BotAction]:
        """Deserialize a unique list of action configurations."""
        if not isinstance(actions_data, list) or not all(
            isinstance(action, dict) for action in actions_data
        ):
            raise ValueError("Config 'actions' must be a list of action dictionaries.")
        actions = [cls.from_dict(action) for action in actions_data]
        action_types = [action.action_type for action in actions]
        if len(action_types) != len(set(action_types)):
            raise ValueError("Config 'actions' cannot contain duplicate action types.")
        return actions

    @staticmethod
    def _read_enabled(action_dict: dict[str, Any]) -> bool:
        enabled = action_dict.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("Action 'enabled' must be a boolean.")
        return enabled

@dataclass
class DeleteAction(BotAction):
    @property
    def action_type(self) -> Literal['delete']:
        return 'delete'

    def to_dict(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, action_dict: dict[str, Any]) -> DeleteAction:
        if action_dict.get("action_type") != "delete":
            raise ValueError("DeleteAction requires action_type='delete'.")
        return cls(enabled=cls._read_enabled(action_dict))


@dataclass
class TimeoutAction(BotAction):
    """Sets a member's timeout
    Parameters:
        duration (int) : Time in minutes for how long the timeout lasts
        reason (str) : The reason shown in the audit log
    """
    duration: int = 60
    reason: str = "Automod rule triggered"

    @property
    def action_type(self) -> Literal['timeout']:
        return 'timeout'

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "enabled": self.enabled,
            "duration": self.duration,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, action_dict: dict[str, Any]) -> TimeoutAction:
        if action_dict.get("action_type") != "timeout":
            raise ValueError("TimeoutAction requires action_type='timeout'.")
        duration = action_dict.get("duration")
        reason = action_dict.get("reason")
        if type(duration) is not int or duration < 1:
            raise ValueError("Timeout action 'duration' must be a positive integer.")
        if not isinstance(reason, str):
            raise ValueError("Timeout action 'reason' must be a string.")
        return cls(
            enabled=cls._read_enabled(action_dict),
            duration=duration,
            reason=reason,
        )


@dataclass
class DMAction(BotAction):
    response_template: str = "Please follow the server rules, <@{user_id}>."

    @property
    def action_type(self) -> Literal['dm']:
        return 'dm'

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "enabled": self.enabled,
            "response_template": self.response_template,
        }

    @classmethod
    def from_dict(cls, action_dict: dict[str, Any]) -> DMAction:
        if action_dict.get("action_type") != "dm":
            raise ValueError("DMAction requires action_type='dm'.")
        response_template = action_dict.get("response_template")
        if not isinstance(response_template, str):
            raise ValueError("DM action 'response_template' must be a string.")
        return cls(
            enabled=cls._read_enabled(action_dict),
            response_template=response_template,
        )

    def format_response(self, values: dict[str, str | int | float]) -> str:
        return safe_format(
            self.response_template,
            values,
            "Please follow the server rules, <@{user_id}>.",
        )


@dataclass
class MessageAction(BotAction):
    """Sends a message in the channel triggered"""
    response_template: str = "<@{user_id}>, please follow the server rules."

    @property
    def action_type(self) -> Literal['message']:
        return 'message'

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "enabled": self.enabled,
            "response_template": self.response_template,
        }

    @classmethod
    def from_dict(cls, action_dict: dict[str, Any]) -> MessageAction:
        if action_dict.get("action_type") != "message":
            raise ValueError("MessageAction requires action_type='message'.")
        response_template = action_dict.get("response_template")
        if not isinstance(response_template, str):
            raise ValueError("Message action 'response_template' must be a string.")
        return cls(
            enabled=cls._read_enabled(action_dict),
            response_template=response_template,
        )

    def format_response(self, values: dict[str, str | int | float]) -> str:
        return safe_format(
            self.response_template,
            values,
            "<@{user_id}>, please follow the server rules.",
        )


BOT_ACTION_TYPES: dict[str, type[BotAction]] = {
    "delete": DeleteAction,
    "timeout": TimeoutAction,
    "dm": DMAction,
    "message": MessageAction,
}

@dataclass
class BaseAutomodComponentConfig(ABC):
    COMPONENT_KEY: ClassVar[str] = ""
    RESPONSE_PLACEHOLDERS: ClassVar[tuple[str, ...]] = ("user_id",) # Available action-template placeholders
    enabled : bool
    guild_id : str # guild for which the config belongs
    is_global : bool # whether or not the automod affects all the channels of a guild
    affected_channels : OrderedSet # can include categories
    ignored_channels : OrderedSet # Does nothing if is_global is False
    logging_channel : str | None # channel id | channel where automod logs are sent.
    ignored_roles : OrderedSet # roles unaffected by the automod
    actions: list[BotAction]

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

    COMPONENT_KEY: ClassVar[str] = ""

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
            raise NotImplementedError((f"Config Key mismatch detected.\nComponent key: {self.COMPONENT_KEY}"
                                       f"\nPassed Config key: {self.config.COMPONENT_KEY}\nMake sure you implemented the automod component properly."))

    def _config_key_matches(self) -> bool:
        "Method used to check if the config key of the automod component matches that of the config"
        return self.COMPONENT_KEY == self.config.COMPONENT_KEY

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


    def initialize_channel_helpers(self, guild:Guild) -> bool:
        "Synchronizes managers with the guild's eligible channels."
        if self.config.enabled:

            for channel in guild.channels:
                if self.is_channel_watched(channel):
                    self.add_manager(str(channel.id))
            print(f"Enabling the helpers for {type(self)}")
        else:
            # Clears all channel helpers if component is disabled.
            print(f"Disabling the helpers for {type(self)}")
            self.channels.clear()

        return self.config.enabled

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
        if not self.config.enabled:
            return AutomodResponse(False, "Automod Component is disabled", None, None)

        elif str(channel.guild.id) != str(guild.id):
            return AutomodResponse(False, "Channel does not belong to the provided guild", None, None)

        channel_manager = self.get_manager(str(channel.id))
        if channel_manager is None and self.is_channel_watched(channel):
            # Channel was created (or moved into a watched category) after the managers were initialized
            self.add_manager(str(channel.id))
            channel_manager = self.get_manager(str(channel.id))

        if channel_manager is None:
            return AutomodResponse(False, "Channel is not watched", None, None)

        user = message.author
        if not isinstance(user, Member):
            return AutomodResponse(False, "Message was not sent in a guild...", None, None)

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
        from config import get_component_related_class

        ComponentClass = get_component_related_class(config.COMPONENT_KEY, 'component_type')
        if issubclass(ComponentClass, BaseAutomodComponent):
            
            return ComponentClass(config, guild, memory)
        else:
            raise TypeError(f"from_config method meant to return AutomodComponent type class but returned {type(ComponentClass)} instead.")

    def __str__(self) -> str:

        return f"{self.COMPONENT_KEY} - {self.config.guild_id}"
