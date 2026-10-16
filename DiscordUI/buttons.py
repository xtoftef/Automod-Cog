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
        await self.panel.engine.set_config(self.panel.guild, self.panel.draft_config)
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

