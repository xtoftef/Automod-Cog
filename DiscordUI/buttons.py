from __future__ import annotations # Needed for the TYPE_CHECKING-only type hints on Python < 3.14

from typing import Any, Callable, TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from .views import AutomodComponentConfigPanelView, MasterPanelView, AutomodLogView
    from src.automod_models import BaseAutomodComponentConfig
    from src.automod_engine import AutomodEngine
from DiscordUI.modals import DMInputModal, CommentInputModal, TimeoutHandlerModal

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
        await interaction.response.defer()
        saved = await self.panel.engine.set_config(self.panel.guild, self.panel.draft_config)
        if not saved:
            # Keep the panel open so the admin can retry instead of believing it was saved
            self.panel.status_display.content = "❌ Could not save the config. Apologies for the error"
            await interaction.edit_original_response(view=self.panel)
            return

        master = self.panel.master_panel
        if master:
            new_state = "enabled" if self.panel.draft_config.enabled else "disabled"
            action_row: discord.ui.ActionRow = master.segments[self.panel.draft_config.COMPONENT_KEY]['action_row']
            if len(action_row.children) > 1: prev_state = new_state # more than one button means component config existed
            else: prev_state = 'inexistent' # Only 1 button means there's only a create button
            await master.modify_buttons(self.panel.draft_config.COMPONENT_KEY, new_state, prev_state) # Need to add a fix there, that properly defines the new and previous states.
            self._write_master_edit_cfg(self.panel.draft_config)
            
            master.panel_state_display.content = "☑️ Panel can be edited again"
            master.frozen = False
            master.refresh_display()
            
            await master.interaction.edit_original_response(view=master)
        self.panel.finish("✅ Saved to the engine.")
        await interaction.edit_original_response(view=self.panel)


class CancelConfigButton(discord.ui.Button):
    def __init__(self, panel: AutomodComponentConfigPanelView) -> None:
        super().__init__(label="Cancel", style=discord.ButtonStyle.danger)
        self.panel = panel
        
    async def callback(self, interaction: discord.Interaction) -> None:
        #self.panel.draft_config = self.panel.engine.cancel_config() # just logging
        await interaction.response.defer()

        self.panel.finish("🚫 Draft changes cancelled; restored the last saved state.")
        master = self.panel.master_panel
        if master:
            master.panel_state_display.content = "☑️Panel can be edited again"
            master.frozen = False
            await master.interaction.edit_original_response(view= master)
            
        await interaction.edit_original_response(view=self.panel)


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



class SendDMButton(discord.ui.Button):
    "Opens a simple modal to input text for a custom DM to be sent via the bot."

    def __init__(self, user: discord.Member, style: discord.ButtonStyle = discord.ButtonStyle.secondary, label: str | None = "SendDM"):
        super().__init__(style=style, label=label)
        self.user = user
        self.panel : AutomodLogView |None = None

    async def callback(self, interaction: discord.Interaction) -> Any:
        "Opens the modal"
        modal = DMInputModal(self.user)
        if self.panel:
            modal.panel = self.panel
        await interaction.response.send_modal(modal)

class AcknowledgeButton(discord.ui.Button):
    "Simply marks an automod log as handled/reviewed by a moderator."
    def __init__(self, style: discord.ButtonStyle = discord.ButtonStyle.primary, label: str | None = "Acknowledge"):
        super().__init__(style=style, label=label)
        self.panel : AutomodLogView |None = None

    async def callback(self, interaction: discord.Interaction) -> Any:
        "Opens the modal"
        modal = CommentInputModal()
        if self.panel:
            modal.panel = self.panel
        await interaction.response.send_modal(modal)

class HandleTimeoutButton(discord.ui.Button):
    "Opens a simple modal to input text for a custom DM to be sent via the bot."

    def __init__(self, user: discord.Member, timeout_success: bool,style: discord.ButtonStyle = discord.ButtonStyle.danger):
        if user.is_timed_out() or timeout_success:
            label = "Remove Timeout" 
        else:
            label = "Timeout"
        super().__init__(style=style, label=label)
        self.user = user
        self.timeout_success = timeout_success
        self.panel : AutomodLogView |None = None

    async def callback(self, interaction: discord.Interaction) -> Any:
        "Opens the modal"
        timeout_checked = False
        if self.panel:
            timeout_checked = self.panel.timeout_checked
        if not self.user.is_timed_out() and self.timeout_success and not timeout_checked:
            # Handle the event when a moderator attempts to remove a timeout but the user already left timeout.

            if self.panel:
                self.panel.timeout_checked = True
                self.panel.remove_timeout_button.label = "Timeout"
                self.panel.timeout_text.content += " **EXPIRED/REMOVED**"  
                await interaction.response.edit_message(view = self.panel)    

            await interaction.followup.send(
                content= "⚠️User's timeout has already ran out or was removed manually. Panel was refreshed accordingly, but reconsider the action",
                ephemeral=True
            )
            return
        modal = TimeoutHandlerModal(self.user)
        if self.panel:
            modal.panel = self.panel
        await interaction.response.send_modal(modal)