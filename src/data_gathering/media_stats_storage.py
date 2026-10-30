"""Implementations of the BaseMediaStatsStorage class."""
import json
import logging
import os

from src.data_gathering.media_stats_models import (
    BaseMediaStatsStorage,
    ChannelStats,
    MediaCounts,
    WatchSession,
)

# Same namespace as logger.get_logger(). Not importing logger.py since it imports config.py, which imports this file.
logger = logging.getLogger("automod.data_gathering.storage")


class JSONMediaStatsStorage(BaseMediaStatsStorage):
    """Stores the media stats in a JSON file shaped like:
    {
        "watches": {channel_id: {"guild_id", "started_at", "ends_at"}},
        "stats": {channel_id: {day: {user_id: {"gif", "image", "video"}}}}
    }"""

    def __init__(self, file_path: str) -> None:
        super().__init__()
        self.file_path = file_path
        self.loaded_memory: dict[str, dict]
        self.dirty = False # True when there are counts that weren't written to the file yet
        self.load_memory()

    def load_memory(self) -> None:
        try:
            with open(self.file_path, "r") as f:
                loaded = json.load(f)
        except FileNotFoundError:
            loaded = {}

        if not isinstance(loaded, dict):
            raise ValueError(f"Media stats file must contain a JSON object: {self.file_path}")
        loaded.setdefault("watches", {})
        loaded.setdefault("stats", {})
        self.loaded_memory = loaded

    def save_memory(self) -> None:
        # Same approach as JSONMemoryManager: write to a temporary file, then swap it in.
        temp_path = self.file_path + ".tmp"
        try:
            with open(temp_path, "w") as f:
                json.dump(self.loaded_memory, f, indent=2)
            os.replace(temp_path, self.file_path)
        except OSError as e:
            logger.error("Ran into an error while trying to save the media stats file. Passed path: %s", self.file_path, exc_info=True)
            raise e
        self.dirty = False
        logger.debug("Saved media stats to %s", self.file_path)

    def get_watches(self) -> dict[str, WatchSession]:
        watches: dict[str, WatchSession] = {}
        for channel_id, data in self.loaded_memory["watches"].items():
            try:
                watches[channel_id] = WatchSession.from_dict(channel_id, data)
            except (KeyError, ValueError, TypeError) as e:
                logger.warning("Skipping anomalous watch session. Channel ID: %s, Error: %r", channel_id, e)
        return watches

    def set_watch(self, session: WatchSession) -> None:
        self.loaded_memory["watches"][session.channel_id] = session.to_dict()
        self.save_memory()

    def add_counts(self, channel_id: str, day: str, user_id: str, counts: MediaCounts) -> None:
        day_stats = self.loaded_memory["stats"].setdefault(channel_id, {}).setdefault(day, {})
        user_counts = MediaCounts.from_dict(day_stats.get(user_id, {}))
        user_counts.merge(counts)
        day_stats[user_id] = user_counts.to_dict()
        self.dirty = True

    def get_channel_stats(self, channel_id: str) -> ChannelStats:
        channel_stats: ChannelStats = {}
        for day, users in self.loaded_memory["stats"].get(channel_id, {}).items():
            channel_stats[day] = {
                user_id: MediaCounts.from_dict(counts) for user_id, counts in users.items()
            }
        return channel_stats

    def flush(self) -> None:
        if self.dirty:
            self.save_memory()
