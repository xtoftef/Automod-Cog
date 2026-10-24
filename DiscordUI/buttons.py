from __future__ import annotations # Needed for the TYPE_CHECKING-only type hints on Python < 3.14

from typing import Callable, TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from .views import AutomodComponentConfigPanelView, MasterPanelView
    from src.automod_models import BaseAutomodComponentConfig
    from src.automod_engine import AutomodEngine

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


class SaveConfigButton(discord.ui.Button):
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        super().__init__(label="Save", style=discord.ButtonStyle.success)
        self.panel = panel

    def _write_master_edit_cfg(self, new_cfg:BaseAutomodComponentConfig):
        master = self.panel.master_panel
        if not master: return
        
        action_row: discord.ui.ActionRow = master.segments[new_cfg.COMPONENT_KEY]['action_row']

        edit_btn = action_row.children[1]
        if isinstance(edit_btn, OpenConfigViewButton):
            edit_btn.cfg = new_cfg

    async def callback(self, interaction: discord.Interaction) -> None:
        saved = await self.panel.engine.set_config(self.panel.guild, self.panel.draft_config)
        if not saved:
            # Keep the panel open so the admin can retry instead of believing it was saved
            self.panel.status_display.content = "❌ Could not save the config. Aplogies for the error"
            await interaction.response.edit_message(view=self.panel)
            return

        master = self.panel.master_panel
        if master:
            await master.modify_buttons(self.panel.draft_config.COMPONENT_KEY, 'enabled', 'inexistent')
            self._write_master_edit_cfg(self.panel.draft_config)
            
            master.panel_state_display.content = "☑️ Panel can be edited again"
            master.frozen = False
            master.refresh_display()
            
            await master.interaction.edit_original_response(view= master)
        self.panel.finish("✅ Saved to the engine.")
        await interaction.response.edit_message(view=self.panel)


class CancelConfigButton(discord.ui.Button):
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        super().__init__(label="Cancel", style=discord.ButtonStyle.danger)
        self.panel = panel
        
    async def callback(self, interaction: discord.Interaction) -> None:
        #self.panel.draft_config = self.panel.engine.cancel_config() # just logging
        self.panel.finish("🚫 Draft changes cancelled; restored the last saved state.")
        master = self.panel.master_panel
        if master:
            master.panel_state_display.content = "☑️Panel can be edited again"
            master.frozen = False
            await master.interaction.edit_original_response(view= master)
            
        await interaction.response.edit_message(view=self.panel)


class EnableButton(discord.ui.Button):
    def __init__(
        self,
        component_key : str,
        panel: MasterPanelView,
        engine: AutomodEngine
    ) -> None:
        super().__init__(label="Enable", style=discord.ButtonStyle.success)
        self.panel = panel
        self.component_key = component_key
        self.engine = engine

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.engine.enable_component(self.panel.guild, self.component_key)

        await self.panel.modify_buttons(self.component_key, 'enabled', 'disabled')

        await interaction.response.edit_message(view=self.panel)

class DisableButton(discord.ui.Button):
    def __init__(
        self,
        component_key : str,
        panel: MasterPanelView,
        engine: AutomodEngine
    ) -> None:
        super().__init__(label="Disable", style=discord.ButtonStyle.danger)
        self.panel = panel
        self.component_key = component_key
        self.engine = engine

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.engine.disable_component(self.panel.guild, self.component_key )

        await self.panel.modify_buttons(self.component_key, 'disabled', 'enabled')

        await interaction.response.edit_message(view=self.panel)
        

class OpenConfigViewButton(discord.ui.Button):
    def __init__(
        self,
        master : MasterPanelView,
        label: str,
        cfg: BaseAutomodComponentConfig,
        engine : AutomodEngine
    ) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.cfg = cfg
        self.automod_engine = engine
        self.master = master


    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Works only in guilds", ephemeral=True)
            return

        
        await interaction.response.send_message(
            view=self.master.get_automod_config_view(self.cfg, self.automod_engine, interaction.user.id, interaction.guild),
            ephemeral=True,
        )
        
        self.master.frozen = True

        self.master.panel_state_display.content = "⚠️ __**PANEL IS CURRENTLY FROZEN**__ ⚠️\n-# Finish using the other panel to unfreeze. "
        await self.master.interaction.edit_original_response(view = self.master)


class CreateConfigViewButton(OpenConfigViewButton):

    def __init__(
        self,
        master: MasterPanelView,
        label: str,
        guild_id:str,
        component_key: str,
        engine : AutomodEngine
    ) -> None:
        from config import ENGINE_CONFIG
        ConfigClass = ENGINE_CONFIG["components"][component_key]["config_type"]
        cfg = ConfigClass.get_default(guild_id)

        super().__init__(master, label, cfg, engine)

