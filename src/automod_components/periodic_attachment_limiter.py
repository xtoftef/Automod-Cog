"""Periodic media-message quota automod component.
Each user's quota can be limited per channel or shared across watched channels.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import ClassVar, Literal
from discord import Guild, Attachment, Embed, Message, Member
from collections import OrderedDict
import logging
import mimetypes
import re
import time
import discord

from src.automod_models import (
    AutomodResponse,
    BotAction,
    DeleteAction,
    MessageAction,
    OrderedSet,
    BaseAutomodComponentConfig,
    BaseAutomodMemoryManager,
    BaseAutomodComponent,
    BaseChannelManager
)

MediaType = Literal['gif', 'image', 'video']
logger = logging.getLogger("automod.Periodic-Attachment-Limiter")
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

@dataclass
class PeriodicAttachmentLimitComponentConfig(BaseAutomodComponentConfig):
    """Config for the periodic attachment limit. 
    Arguments:
        attachment_limit_count (int) : Defines how many messages a user can send within the period duration, that contain media the automod flags.
        period_duration_minutes (int): how often the count of attachments for all users resets.
        share_quota_across_channels (bool): whether the per-user quota is shared across watched channels.
    """

    DEFAULT_MSG_RESPONSE = ("<@{user_id}>, you reached your limit of messages containing attachments ({limit})!  "
        "Next limit refresh: {next_refresh}")
    COMPONENT_KEY: ClassVar[str] = "periodic_attachment_limiter"
    RESPONSE_PLACEHOLDERS: ClassVar[tuple[str, ...]] = ("user_id", "limit", "next_refresh") # NOTE: next_refresh is a derived value which is more relevant for users than the periodic duration
    attachment_limit_count : int 
    period_duration_minutes : int # Duration of the period in minutes
    share_quota_across_channels: bool


    @classmethod
    def get_default(cls, guild_id: str) -> PeriodicAttachmentLimitComponentConfig:
        return cls(
            guild_id= guild_id,
            is_global= True,
            enabled = True,
            affected_channels= OrderedSet(),
            ignored_channels= OrderedSet(),
            logging_channel = None,
            ignored_roles= OrderedSet(),
            actions=[
                DeleteAction(),
                MessageAction(response_template=cls.DEFAULT_MSG_RESPONSE),
            ],
            attachment_limit_count = 100, #100 messages that can contain any amount of media
            period_duration_minutes = 1440, # 1440 minutes = 1 day
            share_quota_across_channels=False,
        )

    def to_dict(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "is_global": self.is_global,
            "enabled" : self.enabled,
            "affected_channels": list(self.affected_channels),
            "ignored_channels": list(self.ignored_channels),
            "ignored_roles": list(self.ignored_roles),
            "logging_channel" : self.logging_channel,
            "actions": [action.to_dict() for action in self.actions],
            "attachment_limit_count": self.attachment_limit_count,
            "period_duration_minutes": self.period_duration_minutes,
            "share_quota_across_channels": self.share_quota_across_channels,
        }

    @classmethod
    def from_dict(cls, config_dict: dict) -> PeriodicAttachmentLimitComponentConfig:
        if not isinstance(config_dict, dict):
            raise ValueError("PeriodicAttachmentLimitComponentConfig.from_dict expects a dictionary.")

        required_keys = {
            "guild_id",
            "is_global",
            "enabled",
            "affected_channels",
            "ignored_channels",
            "logging_channel",
            "ignored_roles",
            "actions",
            "attachment_limit_count",
            "period_duration_minutes",
        }
        missing_keys = sorted(required_keys - config_dict.keys())
        if missing_keys:
            raise ValueError(f"Missing required config keys: {', '.join(missing_keys)}")

        return cls(
            guild_id=str(config_dict["guild_id"]),
            is_global=bool(config_dict["is_global"]),
            enabled = bool(config_dict['enabled']),
            affected_channels=OrderedSet(config_dict.get("affected_channels", [])),
            ignored_channels=OrderedSet(config_dict.get("ignored_channels", [])),
            logging_channel = config_dict.get("logging_channel", None),
            ignored_roles=OrderedSet(config_dict.get("ignored_roles", [])),
            actions=BotAction.list_from_dict(config_dict["actions"]),
            attachment_limit_count = int(config_dict["attachment_limit_count"]),
            period_duration_minutes = int(config_dict["period_duration_minutes"]),
            share_quota_across_channels=bool(
                config_dict.get("share_quota_across_channels", False)
            ),
        )

    def format_unique_config_display(self) -> str:
        return (f"**Media Messages Limit:** `{self.attachment_limit_count}` media messages\n"
                f"**User's Media Counter Resets Every:** `{self.period_duration_minutes}` minutes\n"
                f"**Quota Scope:** `{'all configured channels' if self.share_quota_across_channels else 'each channel separately'}`")


class ChannelPeriodicAttachmentTracker(BaseChannelManager):
    """Tracks per-user media message counts for one quota scope."""

    def __init__(self, channel_id: str, config: PeriodicAttachmentLimitComponentConfig):
        super().__init__(channel_id, config)
        self.config: PeriodicAttachmentLimitComponentConfig
        self.users: OrderedDict[str, int] = OrderedDict() # user_id -> attachment_count
        self.next_refresh = time.time() + (self.config.period_duration_minutes * 60) 

    def _reset_counter(self) -> None:
        """Refreshes the counter for all users"""
        self.users: OrderedDict[str, int] = OrderedDict()

    def process_message(self, user_id: str ,is_immune: bool) -> bool:
        """Processes an incoming media message.

        Returns True if the user's message exceeds the attachment limit (should be blocked), False otherwise.
        Immune users are never flagged"""
        now = time.time()
        if now > self.next_refresh:
            self._reset_counter()
            self.next_refresh = time.time() + (self.config.period_duration_minutes * 60) 


        user_count = self.users.get(user_id, 0)

        if user_count >= self.config.attachment_limit_count and not is_immune:
            return True
        else:
            # NOTE: still increment count even for immune users, it could be helpful in the future for auditing
            user_count += 1
            self.users[user_id] = user_count
            return False



class PeriodicAttachmentLimiterComponent(
    BaseAutomodComponent[ChannelPeriodicAttachmentTracker, PeriodicAttachmentLimitComponentConfig]
):
    """Limits per-user media messages per period, per channel or across watched channels."""
    COMPONENT_KEY: ClassVar[str] = PeriodicAttachmentLimitComponentConfig.COMPONENT_KEY
    def __init__(
        self,
        config: PeriodicAttachmentLimitComponentConfig | None,
        guild: Guild,
        memory: BaseAutomodMemoryManager,
    ) -> None:
        if config is None:
            config = PeriodicAttachmentLimitComponentConfig.get_default(str(guild.id))
        self.global_tracker: ChannelPeriodicAttachmentTracker | None = None
        super().__init__(config, guild, memory)

    @classmethod
    async def create(
        cls,
        guild: Guild,
        memory: BaseAutomodMemoryManager,
    ) -> PeriodicAttachmentLimiterComponent:
        config = await memory.global_get_config(
            str(guild.id),
            PeriodicAttachmentLimitComponentConfig,
        )
        return cls(config,guild, memory)

    def add_manager(self, channel_id: str):
        if self.config.share_quota_across_channels:
            if self.global_tracker is None or not any(
                manager is self.global_tracker for manager in self.channels.values()
            ):
                self.global_tracker = ChannelPeriodicAttachmentTracker(
                    str(channel_id),
                    self.config,
                )
            self.channels[channel_id] = self.global_tracker
            return

        self.channels[channel_id] = ChannelPeriodicAttachmentTracker(
            str(channel_id),
            self.config
        )


    @staticmethod
    def is_media_attachment(attachment: Attachment) -> bool:
        content_type = (attachment.content_type or mimetypes.guess_type(attachment.filename)[0] or "").lower()
        return (
            content_type == "image/gif"
            or content_type.startswith("image/")
            or content_type.startswith("video/")
        )

    def check_for_attachment(self, attachment: Attachment) -> bool:
        "check if it is an attachment type we flag"
        content_type = (attachment.content_type or mimetypes.guess_type(attachment.filename)[0] or "").lower()
        is_media = self.is_media_attachment(attachment)
        if is_media:
            logger.debug(f"Message has attachment of type: {content_type}")
        return is_media

    @staticmethod
    def is_media_embed(embed: Embed) -> bool:
        return embed.type in ("gifv", "image", "video")

    def check_for_embed(self, embed: Embed) -> bool:
        "Checks if it is an embed type we flag"
        is_media = self.is_media_embed(embed)
        if is_media:
            logger.debug(f"Message has embed of type: {embed.type}")
        return is_media

    @staticmethod
    def test_media_detection(message: Message) -> tuple[bool, list[str]]:
        """Return the detector result and per-item details for debugging."""
        details: list[str] = []
        attachment_matches = []
        for attachment in message.attachments:
            content_type = (
                attachment.content_type
                or mimetypes.guess_type(attachment.filename)[0]
                or "unknown"
            ).lower()
            is_media = PeriodicAttachmentLimiterComponent.is_media_attachment(attachment)
            attachment_matches.append(is_media)
            details.append(
                f"Attachment `{attachment.filename}` — `{content_type}`: "
                f"{'MATCH' if is_media else 'not media'}"
            )

        embed_matches = []
        for embed in message.embeds:
            is_media = PeriodicAttachmentLimiterComponent.is_media_embed(embed)
            embed_matches.append(is_media)
            details.append(
                f"Embed type `{embed.type}`: {'MATCH' if is_media else 'not media'}"
            )

        flags = any(attachment_matches) or any(embed_matches)
        if not details:
            details.append("No attachments or embeds found.")
        return flags, details


    def check_media(self, message: Message) -> bool:
        "Checks if any media found in the message is one that we consider that should be flagged."
        return (
            any(self.check_for_attachment(attachment) for attachment in message.attachments)
            or any(self.check_for_embed(embed) for embed in message.embeds)
        )

    def should_reprocess_on_edit(self, message: Message) -> bool:
        """Watch unrendered links in monitored channels for a later media embed."""
        return (
            self.config.enabled
            and isinstance(message.channel, discord.abc.GuildChannel)
            and self.is_channel_watched(message.channel)
            and not self.check_media(message)
            and bool(URL_PATTERN.search(message.content))
        )
            


    async def _process_valid_message(
        self,
        channel_manager: ChannelPeriodicAttachmentTracker,
        user: Member,
        message: Message,
        is_immune: bool
    ) -> AutomodResponse:

        logger.debug(f"Processing {message.id}")

        # Text-only messages are never part of a chain, which also breaks any chain they reply to
        if not self.check_media(message):
            return AutomodResponse(False, "Message has no media", None, None)

        has_triggered = channel_manager.process_message(
            str(message.author.id),
            is_immune
        )

        if has_triggered:
            return AutomodResponse(
                True,
                "User has exceeded their  periodic attachment limit",
                list(self.config.actions),
                self.config.logging_channel,
                {
                    "user_id": str(user.id),
                    "limit": self.config.attachment_limit_count,
                    "next_refresh": f"<t:{int(channel_manager.next_refresh)}:R>", # formatted in relative time
                },
            )
        return AutomodResponse(
            False,
            "User did not trigger the automod",
            None,
            None
        )
