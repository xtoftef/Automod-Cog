from __future__ import annotations # Needed for the TYPE_CHECKING-only type hints on Python < 3.14

__all__ = [
    "BaseConfigEditModal",
    "EditGeneralModal",
    "EditChannelsAndRolesModal",
    "EditImageRateLimiterSpecificModal",
    "EditChainPreventionSpecificModal",
    "unique_modal_router"
]

from copy import deepcopy
import math
from collections.abc import Iterable
from typing import Callable, TYPE_CHECKING, cast, ClassVar
from abc import ABC, abstractmethod

import discord
from discord.enums import ChannelType
from src.automod_models import BaseAutomodComponentConfig
from src.automod_components.image_rate_limiter import ImageRateLimiterComponentConfig
from src.automod_components.reply_chain_prevention import ReplyChainPreventionComponentConfig

from .ui_utils import *

if TYPE_CHECKING:
    # Clears out the type check flag while avoiding circular imports
    # NOTE: This can't be used for runtime events such as creating an object of the class or checking instance.
    from .views import AutomodComponentConfigPanelView
    


# =================================================================================
# Shared Modals
# =================================================================================
class BaseConfigEditModal(discord.ui.Modal):
    """Shared behavior for prototype edit modals."""

    def __init__(
        self,
        panel: AutomodComponentConfigPanelView,
        *,
        title: str = "Edit Configuration",
    ) -> None:
        super().__init__(title=title)
        self.panel = panel

    async def refresh_panel(self, interaction: discord.Interaction) -> None:
        self.panel.refresh_display()
        self.panel.status_display.content = "Draft updated. Save to keep this test state."
        await interaction.response.edit_message(view=self.panel)

class EditGeneralModal(BaseConfigEditModal):
    "General settings. Shared by all automod configs."
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        super().__init__(panel, title="Edit General")
        config = panel.draft_config
        
        self.is_global_input = discord.ui.Checkbox(default=config.is_global)

        self.response_template_input = discord.ui.TextInput(
            default=config.message_response_template,
            placeholder="Message sent when this automod triggers",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=2000,
        )
        self.add_item(
            discord.ui.Label(
                text="Affects all channels (global)",
                description="You can still ignore the channels of your choice in the next section",
                component=self.is_global_input,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Response message",
                description=("Placeholders: " + ", ".join(
                    f"{{{placeholder}}}" for placeholder in config.RESPONSE_PLACEHOLDERS
                ))[:100], # Discord's label description limit
                component=self.response_template_input,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.panel.draft_config.is_global = self.is_global_input.value
        self.panel.draft_config.message_response_template = (
            self.response_template_input.value
        )
        await self.refresh_panel(interaction)


class EditChannelsAndRolesModal(BaseConfigEditModal):
    "General modal for modifying affected channel and roles. Shared by all automod components"
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        super().__init__(panel, title="Edit Channels and Roles")
        config = panel.draft_config
        self.affected_channels_input = discord.ui.ChannelSelect(
            custom_id="affected_channels",
            placeholder="Select channels affected by this automod",
            channel_types=VALID_CHANNEL_TYPES,
            min_values=0,
            max_values=25,
            default_values=_channel_select_defaults(
                panel.guild, config.affected_channels
            ),
        )
        self.ignored_channels_input = discord.ui.ChannelSelect(
            custom_id="ignored_channels",
            placeholder="Select channels ignored by this automod",
            channel_types=VALID_CHANNEL_TYPES,
            min_values=0,
            max_values=25,
            default_values=_channel_select_defaults(
                panel.guild, config.ignored_channels
            ),
        )
        self.ignored_roles_input = discord.ui.RoleSelect(
            custom_id="ignored_roles",
            placeholder="Select roles ignored by this automod",
            min_values=0,
            max_values=25,
            default_values=_role_select_defaults(
                panel.guild, config.ignored_roles
            ),
        )
        self.add_item(
            discord.ui.Label(
                text="Affected channels",
                description="Used when global mode is off.",
                component=self.affected_channels_input,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Ignored channels",
                description="Ignored even when global mode is on.",
                component=self.ignored_channels_input,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Ignored roles",
                description="Members with these roles are exempt.",
                component=self.ignored_roles_input,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.panel.draft_config.affected_channels = type(
            self.panel.draft_config.affected_channels
        )(str(channel.id) for channel in self.affected_channels_input.values)
        self.panel.draft_config.ignored_channels = type(
            self.panel.draft_config.ignored_channels
        )(str(channel.id) for channel in self.ignored_channels_input.values)
        self.panel.draft_config.ignored_roles = type(
            self.panel.draft_config.ignored_roles
        )(str(role.id) for role in self.ignored_roles_input.values)
        await self.refresh_panel(interaction)


# =================================================================================
# COMPONENT SPECIFIC MODALS
# =================================================================================
# Base Modal
class BaseComponentSpecificModal(BaseConfigEditModal):
    COMPONENT_KEY: ClassVar[str] = "" # to override
    def __init__(self, panel: AutomodComponentConfigPanelView, *, title: str = "Edit Configuration") -> None:
        super().__init__(panel, title=title)

    @property
    @abstractmethod
    def draft_config(self) -> BaseAutomodComponentConfig:
        """Property designed to fix some of the type hint issues. Just use typing module's cast function to return the correct type."""
        raise NotImplementedError("draft_config attribute was not implemented")
    


# ----------------------------- Image Rate Limiter-----------------------------
class EditImageRateLimiterSpecificModal(BaseComponentSpecificModal):
    "Unique modal for modifying the settings that are unique to the image rate limiter automod component"
    COMPONENT_KEY: ClassVar[str] = ImageRateLimiterComponentConfig.COMPONENT_KEY
    @property
    def draft_config(self) -> ImageRateLimiterComponentConfig:
        return cast(ImageRateLimiterComponentConfig, self.panel.draft_config)

    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        super().__init__(panel, title="Edit Automod Sensitivity")
        config : ImageRateLimiterComponentConfig = self.draft_config
        self.max_images_input = discord.ui.TextInput(
            default=str(config.max_images),
            placeholder="Positive whole number",
            required=True,
            max_length=10,
        )
        self.window_size_input = discord.ui.TextInput(
            default=str(config.window_size),
            placeholder="Positive whole number",
            required=True,
            max_length=10,
        )
        self.duration_input = discord.ui.TextInput(
            default=str(config.duration),
            placeholder="Positive number of seconds",
            required=True,
            max_length=20,
        )
        for label, component in (
            ("Maximum images", self.max_images_input),
            ("Window size in messages", self.window_size_input),
            ("Duration in seconds", self.duration_input),
        ):
            self.add_item(discord.ui.Label(text=label, component=component))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            max_images = int(self.max_images_input.value)
            window_size = int(self.window_size_input.value)
            duration = float(self.duration_input.value)
        except ValueError:
            await interaction.response.send_message(
                "Enter whole numbers for maximum images and window size, "
                "and a number for duration.",
                ephemeral=True,
            )
            return

        if (
            max_images < 1
            or window_size < 1
            or not math.isfinite(duration)
            or duration <= 0
        ):
            await interaction.response.send_message(
                "All sensitivity values must be greater than zero.",
                ephemeral=True,
            )
            return
        
        self.draft_config.max_images = max_images
        self.draft_config.window_size = window_size
        self.draft_config.duration = duration
        await self.refresh_panel(interaction)


# ----------------------------- Chain Prevention -----------------------------
class EditChainPreventionSpecificModal(BaseComponentSpecificModal):
    "Unique modal for modifying the settings that are unique to the chain prevention automod component"
    COMPONENT_KEY: ClassVar[str] = ReplyChainPreventionComponentConfig.COMPONENT_KEY
    @property
    def draft_config(self) -> ReplyChainPreventionComponentConfig:
        return cast(ReplyChainPreventionComponentConfig, self.panel.draft_config)

    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        super().__init__(panel, title="Edit Automod Sensitivity")
        config : ReplyChainPreventionComponentConfig = self.draft_config
        self.max_chain_length_input = discord.ui.TextInput(
            default=str(config.max_chain_length),
            placeholder="Positive whole number",
            required=True,
            max_length=10,
        )
        self.duration_input = discord.ui.TextInput(
            default=str(config.duration),
            placeholder="Positive number of seconds",
            required=True,
            max_length=20,
        )
        for label, component in (
            ("Maximum media messages per chain", self.max_chain_length_input),
            ("Chain memory in seconds", self.duration_input),
        ):
            self.add_item(discord.ui.Label(text=label, component=component))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            max_chain_length = int(self.max_chain_length_input.value)
            duration = float(self.duration_input.value)
        except ValueError:
            await interaction.response.send_message(
                "Enter a whole number for the maximum chain length "
                "and a number for the chain memory.",
                ephemeral=True,
            )
            return

        if (
            max_chain_length < 1
            or not math.isfinite(duration)
            or duration <= 0
        ):
            await interaction.response.send_message(
                "All sensitivity values must be greater than zero.",
                ephemeral=True,
            )
            return

        self.draft_config.max_chain_length = max_chain_length
        self.draft_config.duration = duration
        await self.refresh_panel(interaction)


def unique_modal_router(
    config: BaseAutomodComponentConfig,
) -> type[BaseConfigEditModal]:
    "Router function to return the specific config modal depending on the config type"
    from config import get_component_related_class

    ModalClass = get_component_related_class(config.COMPONENT_KEY, 'modal_type')

    if issubclass(ModalClass, BaseComponentSpecificModal):

        return ModalClass
    
    raise ValueError("Unsupported Component Modal Class passed.")
    
