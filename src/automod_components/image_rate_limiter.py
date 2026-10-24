from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar
from discord import Guild, Message, Member
from collections import deque
import time

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

# ==============================================================================================
# ATTACHMENT MESSAGE WINDOW LIMITER
# ==============================================================================================
@dataclass
class ImageRateLimiterComponentConfig(BaseAutomodComponentConfig):
    """Allows only X amount of image-messages within a window of Y any-messages. Messages are removed from the cache after Z duration.
    Arguments:
        max_images (int) : X amount of images allowed
        window_size (int) : Y amount of any-message allowed
        duration (float) : Z duration in seconds"""

    DEFAULT_MSG_RESPONSE = ("<@{user_id}>, image limit reached! "
        "Maximum {max_images} images allowed within {window_size} messages.")
    COMPONENT_KEY: ClassVar[str] = "image_rate_limiter"
    RESPONSE_PLACEHOLDERS: ClassVar[tuple[str, ...]] = ("user_id", "max_images", "window_size", "duration")

    max_images : int
    window_size : int # messages 
    duration : float
    message_response_template : str

    @classmethod
    def get_default(cls, guild_id: str) -> ImageRateLimiterComponentConfig:
        return cls(
            guild_id= guild_id,
            enabled = True,
            is_global= True,
            affected_channels= OrderedSet(),
            ignored_channels= OrderedSet(),
            logging_channel = None,
            ignored_roles= OrderedSet(),
            max_images= 3,
            window_size= 10,
            duration= 120,
            message_response_template= ImageRateLimiterComponentConfig.DEFAULT_MSG_RESPONSE
            
        )

    def to_dict(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "is_global": self.is_global,
            "enabled" : self.enabled,
            "affected_channels": list(self.affected_channels),
            "ignored_channels": list(self.ignored_channels),
            "logging_channel" : self.logging_channel,
            "ignored_roles": list(self.ignored_roles),
            "message_response_template": self.message_response_template,
            "max_images": self.max_images,
            "window_size": self.window_size,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, config_dict: dict) -> ImageRateLimiterComponentConfig:
        if not isinstance(config_dict, dict):
            raise ValueError("ImageRateLimiterComponentConfig.from_dict expects a dictionary.")

        required_keys = {
            "guild_id",
            "is_global",
            "enabled",
            "affected_channels",
            "ignored_channels",
            "logging_channel",
            "ignored_roles",
            "max_images",
            "window_size",
            "duration",
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
            max_images=int(config_dict["max_images"]),
            window_size=int(config_dict["window_size"]),
            duration=float(config_dict["duration"]),
            message_response_template=str(
                config_dict.get(
                    "message_response_template",
                    config_dict.get("formatted_message_response", ImageRateLimiterComponentConfig.DEFAULT_MSG_RESPONSE),
                )
            ),
        )

    def format_response(self, user_id: str) -> str:
        return safe_format(
            self.message_response_template,
            {
                "user_id": user_id,
                "max_images": self.max_images,
                "window_size": self.window_size,
                "duration": self.duration,
            },
            ImageRateLimiterComponentConfig.DEFAULT_MSG_RESPONSE,
        )

    def format_unique_config_display(self) -> str:
        return (f"**Max Images:** `{self.max_images}`\n"
                f"**Window Size:** `{self.window_size}` messages\n"
                f"**Duration:** `{self.duration}` seconds")

class ChannelMessageWindowLimiter(BaseChannelManager):
    """Manages sliding message window and time expiration for a single channel."""

    def __init__(self, channel_id: str, config: ImageRateLimiterComponentConfig):
        super().__init__(channel_id, config)
        self.config: ImageRateLimiterComponentConfig
        self.queue = deque()  # Stores tuples of (timestamp, has_image)

    def _evict_expired(self) -> None:

        """Remove messages older than duration (Z) seconds."""
        now = time.time()
        while self.queue and (now - self.queue[0][0]) > self.config.duration:
            self.queue.popleft()

    def process_message(self, has_image: bool) -> bool:

        """Processes an incoming message.

        Returns True if rate limited (should be blocked), False otherwise.
        """
        self._evict_expired()

        if has_image:
            current_images = sum(1 for _, img in self.queue if img)
            if current_images >= self.config.max_images:
                return True  # Limit reached

        self.queue.append((time.time(), has_image))

        if len(self.queue) > self.config.window_size:
            self.queue.popleft()

        return False


class ImageRateLimiterComponent(
    BaseAutomodComponent[ChannelMessageWindowLimiter, ImageRateLimiterComponentConfig]
):
    """Automod designed to watch over assigned channels. This class functions as an overall wrapper or manager for smaller workers
    which each keep track of the state of their assigned channels.
    
    """
    COMPONENT_KEY: ClassVar[str] = ImageRateLimiterComponentConfig.COMPONENT_KEY
    def __init__(
        self,
        config: ImageRateLimiterComponentConfig | None,
        guild: Guild,
        memory: BaseAutomodMemoryManager,
        
    ) -> None:
        if config is None:
            config = ImageRateLimiterComponentConfig.get_default(str(guild.id))
        super().__init__(config, guild, memory)

    @classmethod
    async def create(
        cls,
        guild: Guild,
        memory: BaseAutomodMemoryManager,
    ) -> ImageRateLimiterComponent:
        config = await memory.global_get_config(
            str(guild.id),
            ImageRateLimiterComponentConfig,
        )
        return cls(config, guild, memory )

    def add_manager(self, channel_id: str):
        self.channels[channel_id] = ChannelMessageWindowLimiter(
            str(channel_id),
            self.config
        )

    def check_for_image(self, message: Message) -> bool:
        return any(
            att.content_type and att.content_type.startswith("image/")
            for att in message.attachments
        ) or any(embed.type == "image" for embed in message.embeds)        


    async def _process_valid_message(
        self,
        channel_manager: ChannelMessageWindowLimiter,
        user: Member,
        message: Message,
        is_immune: bool
    ) -> AutomodResponse:

        # check if msg has image
        has_image = self.check_for_image(message)

        # Check if msg trips the automod
        if is_immune:
            return AutomodResponse(False, "User has an immunity role", None, None)

        has_triggered = channel_manager.process_message(has_image)

        # Response if user is not immune and tripped the automod
        if has_triggered:
            return AutomodResponse(
                True,
                "Maximum number of images exceeded",
                [
                    DeleteAction(),
                    MessageAction(self.config.format_response(str(user.id)))
                ],
                self.config.logging_channel
            )

        # Normal msg that doesn't trigger the automod
        else:
            return AutomodResponse(
                False,
                "User did not trigger the automod",
                None,
                None
            )

