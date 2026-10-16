from copy import deepcopy
from typing import TYPE_CHECKING

from .ui_utils import *
from .modals import *
from .buttons import *
from src.component_implementations import BaseAutomodComponentConfig

if TYPE_CHECKING:
    from src.automod_engine import AutomodEngine




class AutomodComponentConfigPanelView(discord.ui.LayoutView):
    """Components V2 config panel backed only by DummyAutomodEngine."""

    def __init__(
        self,
        config: BaseAutomodComponentConfig,
        engine: AutomodEngine,
        author_id: int,
        guild: discord.Guild,
    ) -> None:
        
        super().__init__(timeout=300)
        if not engine: 
            engine = DummyAutomodEngine(config)
        self.draft_config = deepcopy(config)
        self.engine = engine
        self.author_id = author_id
        self.guild = guild
        self.general_button = OpenEditModalButton(
            self, "Edit", EditGeneralModal
        )
        self.targets_button = OpenEditModalButton(
            self, "Edit", EditChannelsAndRolesModal
        )
        self.sensitivity_button = OpenEditModalButton(
            self, "Edit", unique_modal_router(config)
        )
        self.save_button = SaveDummyConfigButton(self)
        self.cancel_button = CancelDummyConfigButton(self)
        self.misc_display = discord.ui.TextDisplay("")
        self.targets_display = discord.ui.TextDisplay("")
        self.sensitivity_display = discord.ui.TextDisplay("")
        self.status_display = discord.ui.TextDisplay(
            "Draft changes are not saved."
        )
        self.refresh_display()
        self.add_item(self.build_container())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This prototype config panel belongs to another user.",
                ephemeral=True,
            )
            return False
        return True

    def build_container(self) -> discord.ui.Container:
        component_title = (
            self.draft_config.CONFIG_KEY.removesuffix("_config")
            .replace("_", " ")
            .title()
        )
        return discord.ui.Container(
            # SHARED/INHERITED CONFIG SETTINGS
            discord.ui.TextDisplay(
                f"# {component_title}\n"
                f"**Guild ID:** `{self.draft_config.guild_id}`"
            ),
            discord.ui.Separator(),
            discord.ui.Section( # General settings
                self.misc_display,
                accessory=self.general_button,
            ),
            discord.ui.Separator(),
            discord.ui.Section( # Channel and roles
                self.targets_display,
                accessory=self.targets_button,
            ),

            # CONFIG TYPE SPECIFIC SETTINGS
            discord.ui.Separator(),
            discord.ui.Section( 
                self.sensitivity_display,
                accessory=self.sensitivity_button,
            ),
            discord.ui.Separator(),
            self.status_display,
            discord.ui.ActionRow(self.save_button, self.cancel_button),
            accent_colour=0xCBD4DE,
        )

    def refresh_display(self) -> None:
        config = self.draft_config
        response_template = discord.utils.escape_mentions(
            discord.utils.escape_markdown(config.message_response_template)
        ) or "*Default*"
        self.misc_display.content = (
            "## Miscellaneous\n"
            f"**Affects ALL channels (global):** "
            f"`{'YES' if config.is_global else 'NO'}`\n"
            f"**Response Message:** {response_template}"
        )
        self.targets_display.content = (
            "## Channels and Roles\n"
            f"**Affected Channels ({len(config.affected_channels)}):**\n"
            f"{_format_guild_entities(self.guild, config.affected_channels, entity_type='channel')}\n"
            f"**Ignored Channels ({len(config.ignored_channels)}):**\n"
            f"{_format_guild_entities(self.guild, config.ignored_channels, entity_type='channel')}\n"
            f"**Ignored Roles ({len(config.ignored_roles)}):**\n"
            f"{_format_guild_entities(self.guild, config.ignored_roles, entity_type='role')}"
        )
        self.sensitivity_display.content = (
            f"## Automod Sensitivity\n{config.format_unique_config_display()}"     
        )

    def finish(self, status: str) -> None:
        self.refresh_display()
        self.status_display.content = status
        for button in (
            self.general_button,
            self.targets_button,
            self.sensitivity_button,
            self.save_button,
            self.cancel_button,
        ):
            button.disabled = True
        self.stop()
