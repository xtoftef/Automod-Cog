"""Media stats collector. Watches specific channels for a defined period of time and counts,
per day and per user, how many gifs, images and videos are sent.
The gathered data is meant to help pick sensible limits for the automod components (e.g. a daily attachment limit)."""
from __future__ import annotations

import csv
import io
import logging
import mimetypes
import statistics
import time

from discord import Attachment, Embed, Message, Member

from src.data_gathering.media_stats_models import (
    BaseMediaStatsStorage,
    DaySummary,
    MediaCounts,
    MediaType,
    WatchSession,
)

SECONDS_PER_DAY = 86400

logger = logging.getLogger("automod.data_gathering.collector") # same namespace as logger.get_logger()


def classify_attachment(attachment: Attachment) -> MediaType | None:
    "Returns the media type of an attachment, or None if it's not a gif, image or video (e.g. a text file)."
    content_type = (attachment.content_type or mimetypes.guess_type(attachment.filename)[0] or "").lower()
    if content_type == "image/gif":
        return "gif"
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("video/"):
        return "video"
    return None


def classify_embed(embed: Embed) -> MediaType | None:
    "Returns the media type of a link embed (tenor/giphy gifs, image links, video links). Rich embeds are ignored."
    if embed.type == "gifv":
        return "gif"
    if embed.type == "image":
        url = (embed.url or embed.thumbnail.url or "").lower()
        return "gif" if url.split("?")[0].endswith(".gif") else "image"
    if embed.type == "video":
        return "video"
    return None


def count_media(message: Message, *, attachments: bool = True, embeds: bool = True) -> MediaCounts:
    "Counts every media item of a message. A message with 3 images counts as 3 images."
    counts = MediaCounts()
    if attachments:
        for attachment in message.attachments:
            media_type = classify_attachment(attachment)
            if media_type:
                counts.add(media_type)
    if embeds:
        for embed in message.embeds:
            media_type = classify_embed(embed)
            if media_type:
                counts.add(media_type)
    return counts


class MediaStatsCollector:
    "Manages the watch sessions and routes the messages of watched channels to the storage."

    def __init__(self, storage: BaseMediaStatsStorage) -> None:
        self.storage = storage
        self.watches: dict[str, WatchSession] = storage.get_watches() # channel_id -> session

    def watch_channel(self, guild_id: str, channel_id: str, duration_days: float) -> WatchSession:
        "Starts (or restarts) watching a channel for the given amount of days."
        now = time.time()
        session = WatchSession(
            channel_id=channel_id,
            guild_id=guild_id,
            started_at=now,
            ends_at=now + duration_days * SECONDS_PER_DAY,
        )
        self.storage.set_watch(session)
        self.watches[channel_id] = session
        logger.info("Started watching channel %s (guild %s) for %s days", channel_id, guild_id, duration_days)
        return session

    def unwatch_channel(self, channel_id: str) -> bool:
        "Ends the watch session of a channel early. Returns False if the channel wasn't being watched."
        session = self.watches.get(channel_id)
        now = time.time()
        if not session or not session.is_active(now):
            return False
        session.ends_at = now
        self.storage.set_watch(session)
        logger.info("Stopped watching channel %s (guild %s)", channel_id, session.guild_id)
        return True

    def get_active_session(self, channel_id: str) -> WatchSession | None:
        session = self.watches.get(channel_id)
        if session and session.is_active(time.time()):
            return session
        return None

    def get_guild_sessions(self, guild_id: str) -> list[WatchSession]:
        "Returns all the sessions (active or not) of a guild."
        return [session for session in self.watches.values() if session.guild_id == guild_id]

    def record_message(self, message: Message, *, attachments: bool = True, embeds: bool = True) -> MediaCounts | None:
        """Counts the media of a message if it was sent in a watched channel.
        Returns the counts that were recorded, or None if nothing was recorded."""
        if not isinstance(message.author, Member) or message.author.bot:
            return None
        if not self.get_active_session(str(message.channel.id)):
            return None

        counts = count_media(message, attachments=attachments, embeds=embeds)
        if counts.total == 0:
            return None

        day = message.created_at.date().isoformat() # UTC
        self.storage.add_counts(str(message.channel.id), day, str(message.author.id), counts)
        logger.debug("Recorded %s for user %s in channel %s", counts, message.author.id, message.channel.id)
        return counts

    def flush(self) -> None:
        self.storage.flush()

    def summarize_channel(self, channel_id: str) -> list[DaySummary]:
        "Aggregates the stats of a channel per day, most recent day first."
        summaries: list[DaySummary] = []
        for day, users in sorted(self.storage.get_channel_stats(channel_id).items(), reverse=True):
            totals = MediaCounts()
            per_user = [counts.total for counts in users.values()]
            for counts in users.values():
                totals.merge(counts)
            summaries.append(DaySummary(
                day=day,
                users=len(users),
                totals=totals,
                average_per_user=statistics.mean(per_user) if per_user else 0.0,
                median_per_user=statistics.median(per_user) if per_user else 0.0,
                max_per_user=max(per_user, default=0),
            ))
        return summaries

    def export_csv(self, channel_ids: list[str]) -> str:
        "Flattens the stats of the given channels into CSV (one row per channel, day and user) for spreadsheet analysis."
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["channel_id", "day", "user_id", "gif", "image", "video", "total"])
        for channel_id in channel_ids:
            for day, users in sorted(self.storage.get_channel_stats(channel_id).items()):
                for user_id, counts in users.items():
                    writer.writerow([channel_id, day, user_id, counts.gif, counts.image, counts.video, counts.total])
        return output.getvalue()
