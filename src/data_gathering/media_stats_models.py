"""Data models and the storage template for the media stats data gathering feature.

Stored stats follow the format below (see format.txt):
    channel_id -> day (YYYY-MM-DD, UTC) -> user_id -> {"gif": count, "image": count, "video": count}
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Literal

MediaType = Literal["gif", "image", "video"]

# channel_id -> day -> user_id -> counts
ChannelStats = dict[str, dict[str, "MediaCounts"]]


@dataclass
class MediaCounts:
    "Media counters of a single user for a single day in a single channel."
    MEDIA_TYPES: ClassVar[tuple[MediaType, ...]] = ("gif", "image", "video")

    gif: int = 0
    image: int = 0
    video: int = 0

    @property
    def total(self) -> int:
        return self.gif + self.image + self.video

    def add(self, media_type: MediaType, amount: int = 1) -> None:
        setattr(self, media_type, getattr(self, media_type) + amount)

    def merge(self, other: MediaCounts) -> None:
        "Adds the counters of another MediaCounts to this one."
        for media_type in self.MEDIA_TYPES:
            self.add(media_type, getattr(other, media_type))

    def to_dict(self) -> dict[str, int]:
        return {"gif": self.gif, "image": self.image, "video": self.video}

    @classmethod
    def from_dict(cls, counts_dict: dict) -> MediaCounts:
        if not isinstance(counts_dict, dict):
            raise ValueError("MediaCounts.from_dict expects a dictionary.")
        return cls(
            gif=int(counts_dict.get("gif", 0)),
            image=int(counts_dict.get("image", 0)),
            video=int(counts_dict.get("video", 0)),
        )


@dataclass
class WatchSession:
    """A channel being watched for a defined period of time.
    Sessions are kept after they end, so the stats of a channel can still be traced back to its guild."""
    channel_id: str
    guild_id: str
    started_at: float # unix timestamp
    ends_at: float # unix timestamp

    def is_active(self, now: float) -> bool:
        return self.started_at <= now < self.ends_at

    def to_dict(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "started_at": self.started_at,
            "ends_at": self.ends_at,
        }

    @classmethod
    def from_dict(cls, channel_id: str, session_dict: dict) -> WatchSession:
        if not isinstance(session_dict, dict):
            raise ValueError("WatchSession.from_dict expects a dictionary.")
        return cls(
            channel_id=str(channel_id),
            guild_id=str(session_dict["guild_id"]),
            started_at=float(session_dict["started_at"]),
            ends_at=float(session_dict["ends_at"]),
        )


@dataclass
class DaySummary:
    "Aggregated stats of a channel for a single day. Used to help pick automod limits."
    day: str
    users: int # users that sent at least one media item
    totals: MediaCounts
    average_per_user: float
    median_per_user: float
    max_per_user: int


class BaseMediaStatsStorage(ABC):
    """Base class for the media stats persistent storage.
    Counters are expected to be cached and only written to the storage when flush() is called,
    since writing on every single message would be too heavy for busy channels."""

    @abstractmethod
    def get_watches(self) -> dict[str, WatchSession]:
        "Returns all the watch sessions (active or not), keyed by channel id."

    @abstractmethod
    def set_watch(self, session: WatchSession) -> None:
        "Adds or replaces the watch session of a channel. Persisted immediately."

    @abstractmethod
    def add_counts(self, channel_id: str, day: str, user_id: str, counts: MediaCounts) -> None:
        "Adds the counts to the user's counters for that day and channel."

    @abstractmethod
    def get_channel_stats(self, channel_id: str) -> ChannelStats:
        "Returns the stats of a channel: day -> user_id -> counts. Empty if the channel has no stats."

    @abstractmethod
    def flush(self) -> None:
        "Writes the cached changes to the persistent storage."
