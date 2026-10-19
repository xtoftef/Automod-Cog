from __future__ import annotations # Needed for the TYPE_CHECKING-only type hints on Python < 3.14

from typing import Callable, TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from .views import AutomodComponentConfigPanelView

class OpenEditModalButton(discord.ui.Button):
    def __init__(
        self,
        panel: AutomodComponentConfigPanelView,
        label: str,
        modal_factory: Callable[[AutomodComponentConfigPanelView], discord.ui.Modal],
    ) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.panel = panel
        self.modal_factory = modal_factory

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(self.modal_factory(self.panel))


class SaveDummyConfigButton(discord.ui.Button):
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        super().__init__(label="Save", style=discord.ButtonStyle.success)
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        saved = await self.panel.engine.set_config(self.panel.guild, self.panel.draft_config)
        if not saved:
            # Keep the panel open so the admin can retry instead of believing it was saved
            self.panel.status_display.content = "❌ Could not save the config. Check the bot's console for the error."
            await interaction.response.edit_message(view=self.panel)
            return
        self.panel.finish("✅ Saved to the engine.")
        await interaction.response.edit_message(view=self.panel)


class CancelDummyConfigButton(discord.ui.Button):
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        super().__init__(label="Cancel", style=discord.ButtonStyle.danger)
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        #self.panel.draft_config = self.panel.engine.cancel_config() # just logging
        self.panel.finish("🚫 Draft changes cancelled; restored the last saved test state.")
        await interaction.response.edit_message(view=self.panel)

