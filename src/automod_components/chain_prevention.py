"""Reply chain prevention automod component.
Prevents users from chain replying media messages (attachments, embeds or stickers)."""

from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar
from discord import Guild, Message, Member
from collections import OrderedDict
import time
import discord

from src.automod_models import (
    AutomodResponse,
    DeleteAction,
    TimeoutAction,
    DMAction,
    MessageAction,
    OrderedSet,
    BaseAutomodComponentConfig,
    BaseAutomodMemoryManager,
    BaseAutomodComponent,
    BaseChannelManager
)
from utils import safe_format


@dataclass
class ChainPreventionComponentConfig(BaseAutomodComponentConfig):
    """Prevents linear reply chains of media messages (attachments, embeds or stickers).
    A chain is M1 <- M2 <- M3 ... where each message contains media and replies to the previous one.
    Several replies to the same message (M1 <- M2, M1 <- M3) are separate chains and do not add up.
    Arguments:
        max_chain_length (int) : maximum amount of media messages allowed in a single chain
        duration (float) : seconds a media message is remembered as a possible chain link"""

    DEFAULT_MSG_RESPONSE = ("<@{user_id}>, please don't chain media replies! "
        "Maximum {max_chain_length} media messages per reply chain.")
    CONFIG_KEY: ClassVar[str] = "chain_prevention_config"
    RESPONSE_PLACEHOLDERS: ClassVar[tuple[str, ...]] = ("user_id", "max_chain_length", "duration")

    max_chain_length : int
    duration : float
    message_response_template : str

    @classmethod
    def get_default(cls, guild_id: str) -> ChainPreventionComponentConfig:
        return cls(
            guild_id= guild_id,
            is_global= True,
            affected_channels= OrderedSet(),
            ignored_channels= OrderedSet(),
            ignored_roles= OrderedSet(),
            max_chain_length= 3,
            duration= 600,
            message_response_template= ChainPreventionComponentConfig.DEFAULT_MSG_RESPONSE
        )

    def to_dict(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "is_global": self.is_global,
            "affected_channels": list(self.affected_channels),
            "ignored_channels": list(self.ignored_channels),
            "ignored_roles": list(self.ignored_roles),
            "message_response_template": self.message_response_template,
            "max_chain_length": self.max_chain_length,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, config_dict: dict) -> ChainPreventionComponentConfig:
        if not isinstance(config_dict, dict):
            raise ValueError("ChainPreventionComponentConfig.from_dict expects a dictionary.")

        required_keys = {
            "guild_id",
            "is_global",
            "affected_channels",
            "ignored_channels",
            "ignored_roles",
            "max_chain_length",
            "duration",
        }
        missing_keys = sorted(required_keys - config_dict.keys())
        if missing_keys:
            raise ValueError(f"Missing required config keys: {', '.join(missing_keys)}")

        return cls(
            guild_id=str(config_dict["guild_id"]),
            is_global=bool(config_dict["is_global"]),
            affected_channels=OrderedSet(config_dict.get("affected_channels", [])),
            ignored_channels=OrderedSet(config_dict.get("ignored_channels", [])),
            ignored_roles=OrderedSet(config_dict.get("ignored_roles", [])),
            max_chain_length=int(config_dict["max_chain_length"]),
            duration=float(config_dict["duration"]),
            message_response_template=str(
                config_dict.get("message_response_template", ChainPreventionComponentConfig.DEFAULT_MSG_RESPONSE)
            ),
        )

    def format_response(self, user_id: str) -> str:
        return safe_format(
            self.message_response_template,
            {
                "user_id": user_id,
                "max_chain_length": self.max_chain_length,
                "duration": self.duration,
            },
            ChainPreventionComponentConfig.DEFAULT_MSG_RESPONSE,
        )

    def format_unique_config_display(self) -> str:
        return (f"**Max Chain Length:** `{self.max_chain_length}` media messages\n"
                f"**Chain Memory:** `{self.duration}` seconds")


class ChannelReplyChainTracker(BaseChannelManager):
    """Keeps track of the reply chain depth of recent media messages within a single channel."""

    def __init__(self, channel_id: str, config: ChainPreventionComponentConfig):
        super().__init__(channel_id, config)
        self.config: ChainPreventionComponentConfig
        self.chains: OrderedDict[str, tuple[float, int]] = OrderedDict() # message_id -> (timestamp, chain depth)

    def _evict_expired(self) -> None:
        """Forget media messages older than duration seconds. Insertion order is chronological."""
        now = time.time()
        while self.chains and (now - next(iter(self.chains.values()))[0]) > self.config.duration:
            self.chains.popitem(last=False)

    def process_message(self, message_id: str, replied_to_id: str | None, is_immune: bool) -> bool:
        """Processes an incoming media message.

        Returns True if the message extends a chain past the limit (should be blocked), False otherwise.
        Immune users are never flagged, but their messages still count as chain links."""
        self._evict_expired()

        parent = self.chains.get(replied_to_id) if replied_to_id else None
        depth = parent[1] + 1 if parent else 1

        if depth > self.config.max_chain_length and not is_immune:
            return True # Blocked messages get deleted, so they are not recorded as a link

        self.chains[message_id] = (time.time(), depth)
        return False


class ChainPreventionComponent(
    BaseAutomodComponent[ChannelReplyChainTracker, ChainPreventionComponentConfig]
):
    """Automod that prevents users from chain replying media messages in the watched channels."""
    CONFIG_KEY: ClassVar[str] = ChainPreventionComponentConfig.CONFIG_KEY
    def __init__(
        self,
        guild: Guild,
        memory: BaseAutomodMemoryManager,
        config: ChainPreventionComponentConfig | None = None,
    ) -> None:
        if config is None:
            config = ChainPreventionComponentConfig.get_default(str(guild.id))
        super().__init__(config, guild, memory)

    @classmethod
    async def create(
        cls,
        guild: Guild,
        memory: BaseAutomodMemoryManager,
    ) -> ChainPreventionComponent:
        config = await memory.global_get_config(
            str(guild.id),
            ChainPreventionComponentConfig,
        )
        return cls(guild, memory, config)

    def add_manager(self, channel_id: str):
        self.channels[channel_id] = ChannelReplyChainTracker(
            str(channel_id),
            self.config
        )

    def check_for_media(self, message: Message) -> bool:
        return bool(message.attachments or message.embeds or message.stickers)

    def get_replied_to_id(self, message: Message) -> str | None:
        "Returns the id of the message being replied to. Forwards and other references are ignored."
        if message.type != discord.MessageType.reply or message.reference is None:
            return None
        if message.reference.message_id is None:
            return None
        return str(message.reference.message_id)

    async def _process_valid_message(
        self,
        channel_manager: ChannelReplyChainTracker,
        user: Member,
        message: Message,
        is_immune: bool
    ) -> AutomodResponse:

        # Text-only messages are never part of a chain, which also breaks any chain they reply to
        if not self.check_for_media(message):
            return AutomodResponse(False, "Message has no media", None)

        has_triggered = channel_manager.process_message(
            str(message.id),
            self.get_replied_to_id(message),
            is_immune
        )

        if has_triggered:
            return AutomodResponse(
                True,
                "Chain of reply threshhold was exceeded",
                [
                    DeleteAction(),
                    MessageAction(self.config.format_response(str(user.id)))
                ]
            )
        return AutomodResponse(
            False,
            "User did not trigger the automod",
            None
        )
