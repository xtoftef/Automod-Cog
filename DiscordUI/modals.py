from __future__ import annotations

from discord.utils import MISSING # Needed for the TYPE_CHECKING-only type hints on Python < 3.14

__all__ = [
    "BaseConfigEditModal",
    "EditGeneralModal",
    "EditChannelsAndRolesModal",
    "EditImageRateLimiterSpecificModal",
    "EditChainPreventionSpecificModal",
    "EditDeleteActionModal",
    "EditTimeoutActionModal",
    "EditDMActionModal",
    "EditMessageActionModal",
    "unique_modal_router"
]

import re
from datetime import timedelta
from copy import deepcopy
import math
from collections.abc import Iterable
from typing import Callable, TYPE_CHECKING, cast, ClassVar
from abc import ABC, abstractmethod

import discord
from discord.enums import ChannelType
from src.automod_models import (
    BaseAutomodComponentConfig,
    BotAction,
    DeleteAction,
    TimeoutAction,
    DMAction,
    MessageAction,
)
from src.automod_components.image_rate_limiter import ImageRateLimiterComponentConfig
from src.automod_components.reply_chain_prevention import ReplyChainPreventionComponentConfig

from .ui_utils import *

if TYPE_CHECKING:
    # Clears out the type check flag while avoiding circular imports
    # NOTE: This can't be used for runtime events such as creating an object of the class or checking instance.
    from .views import AutomodComponentConfigPanelView, AutomodLogView
    

# =================================================================================
# Misc Modals
# =================================================================================
class DMInputModal(discord.ui.Modal):
    "Simple modal that prompts for a message to be DM'd to the user"
    def __init__(self, user: discord.Member) -> None:
        super().__init__(title="Send DM to user", timeout=None)
        self.user = user
        self.panel: AutomodLogView | None = None

        self.dm_message_input = discord.ui.TextInput(
            placeholder="Hello, we wish to inform you of...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=2000,
        )

        self.add_item(discord.ui.Label(
            text = "DM message:",
            description="Type your DM message below.",
            component= self.dm_message_input
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        #await interaction.response.defer(ephemeral=True)
        if isinstance(interaction.channel, (discord.ForumChannel, discord.CategoryChannel)): 
            raise Exception("Channel is a forum or category channel, which can't handle this interaction.")
        try:
            embed = discord.Embed(
                title= f"{self.user.guild.name}'s Staff",
                description= f"### The following message was communicated to you:\n\n {self.dm_message_input.value}"
            )
            await self.user.send(embed=embed)
            
            if self.panel:
                self.panel.finish(
                    f"{interaction.user.mention} Sent a DM."
                )
                await interaction.response.edit_message(view= self.panel)


        except discord.Forbidden as e:
            await interaction.response.send_message(content=f"Failed to send the DM to {self.user.mention}.\n User's DMs was closed.", ephemeral=True)
       
class CommentInputModal(discord.ui.Modal):
    "Simple modal that prompts for a message to be DM'd to the user"
    def __init__(self) -> None:
        super().__init__(title="Add an optional reason/comment.", timeout=None)
        self.panel: AutomodLogView | None = None

        self.comment_input = discord.ui.TextInput(
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=300,
        )

        self.add_item(discord.ui.Label(
            text = "Optional comment/reason:",
            component= self.comment_input
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:

        if self.panel:
            self.panel.finish((
                f"{interaction.user.mention} marked as read."
                f"{f"\n**Comment:** {self.comment_input.value}" if self.comment_input.value else ""}"
            ))
            await interaction.response.edit_message(view= self.panel)

class TimeoutHandlerModal(discord.ui.Modal):
    "Simple modal that prompts for a message to be DM'd to the user"
    def __init__(self, user: discord.Member) -> None:
        super().__init__(title="Timeout/Remove timeout from user", timeout=None)
        self.user = user
        self.panel: AutomodLogView | None = None

        self.duration_input: discord.ui.TextInput | None = None
        self.dm_message_input: discord.ui.TextInput | None = None

        self.populate_modal()


    def populate_modal(self) -> None:
        """Simply populates the modal based on the timeout state of the user."""
        if not self.user.is_timed_out():
            # If user is NOT timed out, prompt for timeout duration
            self.duration_input = discord.ui.TextInput(
                default="1h",
                placeholder='"1h", "24h"',
                required=True,
                style=discord.TextStyle.short,
                max_length=10,
            )

            self.add_item(
                discord.ui.Label(
                    text="Timeout Duration:",
                    description='Only supports hours/minutes. Such as "1h"',
                    component=self.duration_input,
                )
            )

        # Reason prompt
        self.reason_input = discord.ui.TextInput(
            placeholder="Type your reason...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=300,
        )

        self.add_item(
            discord.ui.Label(
                text=f"{"Timeout" if self.duration_input else "Timeout removal"} reason:",
                component=self.reason_input,
            )
        )

    def parse_timeout_input(self) -> timedelta | None:
        """Parses duration input like '1h', '24h', or '30m' into a timedelta object."""
        if not self.duration_input or not self.duration_input.value:
            return None

        match = re.match(r"^(\d+)\s*([hm])$", self.duration_input.value.strip().lower())
        if not match:
            return None

        amount, unit = int(match.group(1)), match.group(2)
        if unit == "h":
            return timedelta(hours=amount)
        elif unit == "m":
            return timedelta(minutes=amount)

        return None


    async def on_submit(self, interaction: discord.Interaction) -> None:
        if isinstance(interaction.channel, (discord.ForumChannel, discord.CategoryChannel)):
            raise Exception("Channel is a forum or category channel, which can't handle this interaction.")

        # Handle Timeout State Changes
        if self.user.is_timed_out():
            try:
                await self.user.timeout(None, reason=f"Timeout removed by {interaction.user}")
                action_text = f"{interaction.user.mention} removed the timeout with reason:\n{self.reason_input.value}"
            except discord.Forbidden:
                await interaction.response.send_message(
                    content=f"Failed to remove timeout for {self.user.mention}. Missing permissions.",
                    ephemeral=True,
                )
                return
        else:
            duration = self.parse_timeout_input()
            if duration is None:
                await interaction.response.send_message(
                    content="Invalid duration format. Please use numbers followed by 'h' or 'm' (e.g., '1h', '30m').",
                    ephemeral=True,
                )
                return

            try:
                await self.user.timeout(duration, reason=f"Timed out by {interaction.user}")
                action_text = f"{interaction.user.mention} added a {self.duration_input.value} timeout with reason:\n{self.reason_input.value}" # type: ignore

            except discord.Forbidden:
                await interaction.response.send_message(
                    content=f"Failed to timeout {self.user.mention}. Missing permissions.",
                    ephemeral=True,
                )
                return
            
        if self.panel:
            self.panel.finish(action_text)
            await interaction.response.edit_message(view=self.panel)




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

        self.add_item(
            discord.ui.Label(
                text="Affects all channels (global)",
                description="You can still ignore the channels of your choice in the next section",
                component=self.is_global_input,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.panel.draft_config.is_global = self.is_global_input.value
        await self.refresh_panel(interaction)


class BaseBotActionConfigModal(BaseConfigEditModal):
    """Common enabled-state editing and draft handling for an individual action."""

    def __init__(
        self,
        panel: AutomodComponentConfigPanelView,
        action: BotAction,
        *,
        title: str,
    ) -> None:
        super().__init__(panel, title=title)
        self.action = action
        self.enabled_input = discord.ui.Checkbox(default=action.enabled)
        self.add_item(
            discord.ui.Label(
                text="Action enabled",
                component=self.enabled_input,
            )
        )

    async def save_action(self, interaction: discord.Interaction) -> None:
        self.action.enabled = self.enabled_input.value
        self.panel.set_action_config(self.action)
        await self.refresh_panel(interaction)


class EditDeleteActionModal(BaseBotActionConfigModal):
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        action = next(
            (
                existing for existing in panel.draft_config.actions
                if existing.action_type == "delete"
            ),
            DeleteAction(),
        )
        super().__init__(panel, action, title="Configure Delete Action")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.save_action(interaction)


class EditTimeoutActionModal(BaseBotActionConfigModal):
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        action = next(
            (
                existing for existing in panel.draft_config.actions
                if existing.action_type == "timeout"
            ),
            TimeoutAction(),
        )
        if not isinstance(action, TimeoutAction):
            raise TypeError("Stored timeout action has an invalid type.")
        super().__init__(panel, action, title="Configure Timeout Action")
        self.duration_input = discord.ui.TextInput(
            default=str(action.duration),
            placeholder="1 to 40320 minutes",
            required=True,
            max_length=5,
        )
        self.reason_input = discord.ui.TextInput(
            default=action.reason,
            placeholder="Reason shown in the audit log",
            required=True,
            max_length=300,
        )
        self.add_item(discord.ui.Label(
            text="Duration (minutes)",
            component=self.duration_input,
        ))
        self.add_item(discord.ui.Label(
            text="Audit log reason",
            component=self.reason_input,
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            duration = int(self.duration_input.value)
        except ValueError:
            await interaction.response.send_message(
                "Timeout duration must be a whole number of minutes.",
                ephemeral=True,
            )
            return
        if not 1 <= duration <= 40320:
            await interaction.response.send_message(
                "Timeout duration must be between 1 and 40320 minutes.",
                ephemeral=True,
            )
            return
        if not isinstance(self.action, TimeoutAction):
            raise TypeError("Stored timeout action has an invalid type.")
        self.action.duration = duration
        self.action.reason = self.reason_input.value
        await self.save_action(interaction)


class BaseTemplateActionConfigModal(BaseBotActionConfigModal):
    def __init__(
        self,
        panel: AutomodComponentConfigPanelView,
        action: DMAction | MessageAction,
        *,
        title: str,
    ) -> None:
        super().__init__(panel, action, title=title)
        self.template_input = discord.ui.TextInput(
            default=action.response_template,
            placeholder="Template sent when this automod triggers",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=2000,
        )
        placeholders = ", ".join(
            f"{{{placeholder}}}"
            for placeholder in panel.draft_config.RESPONSE_PLACEHOLDERS
        )
        self.add_item(discord.ui.Label(
            text="Response template",
            description=f"Available placeholders: {placeholders}"[:100],
            component=self.template_input,
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(self.action, (DMAction, MessageAction)):
            raise TypeError("Stored template action has an invalid type.")
        self.action.response_template = self.template_input.value
        await self.save_action(interaction)


class EditDMActionModal(BaseTemplateActionConfigModal):
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        action = next(
            (
                existing for existing in panel.draft_config.actions
                if existing.action_type == "dm"
            ),
            DMAction(),
        )
        if not isinstance(action, DMAction):
            raise TypeError("Stored DM action has an invalid type.")
        super().__init__(panel, action, title="Configure DM Action")


class EditMessageActionModal(BaseTemplateActionConfigModal):
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        action = next(
            (
                existing for existing in panel.draft_config.actions
                if existing.action_type == "message"
            ),
            MessageAction(
                response_template=getattr(
                    panel.draft_config,
                    "DEFAULT_MSG_RESPONSE",
                    MessageAction.response_template,
                )
            ),
        )
        if not isinstance(action, MessageAction):
            raise TypeError("Stored message action has an invalid type.")
        super().__init__(panel, action, title="Configure Channel Message Action")

class EditChannelsAndRolesModal(BaseConfigEditModal):
    "General modal for modifying affected channel and roles. Shared by all automod components"
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        super().__init__(panel, title="Edit Channels and Roles")
        config = panel.draft_config
        logging_channel = []
        if config.logging_channel: logging_channel = [config.logging_channel]
        self.logging_channel_input = discord.ui.ChannelSelect(
            custom_id="logging_channel",
            placeholder="Select the channel in which the automod will log this specific component.",
            channel_types=VALID_CHANNEL_TYPES,
            min_values=0,
            max_values=1,
            default_values = _channel_select_defaults(
                panel.guild, logging_channel
            )
        )
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
                text= "Logging Channel",
                description="The channel in which the automod log will be sent.",
                component=self.logging_channel_input,
            )
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
        # The select allows 0 values, which clears the logging channel
        logging_channels = self.logging_channel_input.values
        self.panel.draft_config.logging_channel = str(logging_channels[0].id) if logging_channels else None
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
    
