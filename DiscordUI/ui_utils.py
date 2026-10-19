"""This file contains relevant utility functions for the UI components."""
from collections.abc import Iterable

import discord
from discord.enums import ChannelType


__all__ = [
    "VALID_CHANNEL_TYPES",
    "_channel_select_defaults",
    "_format_guild_entities",
    "_role_select_defaults"
]


VALID_CHANNEL_TYPES = [
    ChannelType.category, ChannelType.text, ChannelType.forum, ChannelType.voice, ChannelType.stage_voice
]


def _channel_select_defaults(
    guild: discord.Guild, channel_ids: Iterable[str]
) -> list[discord.SelectDefaultValue]:
    defaults: list[discord.SelectDefaultValue] = []
    for channel_id in channel_ids:
        try:
            channel = guild.get_channel(int(channel_id))
        except ValueError:
            continue
        if channel is not None and channel.type in VALID_CHANNEL_TYPES:
            defaults.append(discord.SelectDefaultValue.from_channel(channel))
        else:
            try:
                defaults.append(
                    discord.SelectDefaultValue(
                        id=int(channel_id),
                        type=discord.SelectDefaultValueType.channel,
                    )
                )
            except ValueError:
                continue
    return defaults[:25]


def _role_select_defaults(
    guild: discord.Guild, role_ids: Iterable[str]
) -> list[discord.SelectDefaultValue]:
    defaults: list[discord.SelectDefaultValue] = []
    for role_id in role_ids:
        try:
            role = guild.get_role(int(role_id))
        except ValueError:
            continue
        if role is not None:
            defaults.append(discord.SelectDefaultValue.from_role(role))
        else:
            try:
                defaults.append(
                    discord.SelectDefaultValue(
                        id=int(role_id),
                        type=discord.SelectDefaultValueType.role,
                    )
                )
            except ValueError:
                continue
    return defaults[:25]


def _format_guild_entities(
    guild: discord.Guild,
    ids: Iterable[str],
    *,
    entity_type: str,
) -> str:
    if not ids:
        return "*None*"

    lines: list[str] = []
    for entity_id in ids:
        try:
            snowflake_id = int(entity_id)
        except ValueError:
            lines.append(f"Invalid ID: `{entity_id}`")
            continue

        if entity_type == "channel":
            entity = guild.get_channel(snowflake_id)
            name = entity.name if entity is not None else "Unknown channel"
        else:
            entity = guild.get_role(snowflake_id)
            name = entity.name if entity is not None else "Unknown role"
        lines.append(f"{discord.utils.escape_markdown(name)} (`{entity_id}`)")

    rendered = "\n".join(lines)
    return rendered if len(rendered) <= 900 else rendered[:897] + "..."

