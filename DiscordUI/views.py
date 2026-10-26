from copy import deepcopy
from typing import TYPE_CHECKING, Literal

from .ui_utils import *
from .modals import *
from .buttons import *
from src.automod_models import BaseAutomodComponentConfig

if TYPE_CHECKING:
    from src.automod_engine import AutomodEngine
    from src.automod_models import AutomodLog




class AutomodComponentConfigPanelView(discord.ui.LayoutView):
    """Components V2 config panel used to edit an automod component's config and save it through the engine."""

    def __init__(
        self,
        config: BaseAutomodComponentConfig,
        engine: AutomodEngine,
        author_id: int,
        guild: discord.Guild,
    ) -> None:

        self.master_panel : MasterPanelView | None = None # Convenience attribute in the event where the panel comes from a master panel
        
        super().__init__(timeout=300)
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
        self.save_button = SaveConfigButton(self)
        self.cancel_button = CancelConfigButton(self)
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
            self.draft_config.COMPONENT_KEY.removesuffix("_config")
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
            f"**Logging Channel: {f"<#{config.logging_channel}>" if config.logging_channel else "`None`"}**\n"
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


class MasterPanelView(discord.ui.LayoutView):
    """Components V2 control panel displaying all the available automod components and their status, with the option to edit them"""

    def __init__(
        self,
        engine: AutomodEngine,
        config_list : list[BaseAutomodComponentConfig],
        author_id: int,
        guild: discord.Guild,
        interaction: discord.Interaction
    ) -> None:
        
        super().__init__(timeout=300)
        self.component_buttons = {} # component_key -> button
        self.engine = engine
        self.author_id = author_id
        self.guild = guild
        self.interaction = interaction
        self.config_list = config_list
        self.segments : dict[str, dict] = {} # component key -> segment
        self.frozen = False

        self.panel_state_display = discord.ui.TextDisplay("_ _")

        self.refresh_display()
        self.init_guild_segments()
        self.add_item(self.build_container())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This prototype config panel belongs to another user.",
                ephemeral=True,
            )
            return False

        if self.frozen:
            await interaction.response.send_message(
                "This panel was frozen since you have another panel opened. Finish modifying that one first.",
                ephemeral=True,
            )
            return False
        return True

    STATE_MAP = {
        "enabled" : "✅ **ACTIVE**",
        'disabled': "❌ **INACTIVE**",
        'inexistent' : "🟨 **NOT INITIALIZED**"
    }
    COMPONENT_STATES = Literal['enabled', 'disabled', 'inexistent']
    ID_increment = 00

    async def modify_buttons(self, component_key: str, new_state : COMPONENT_STATES, previous_state : COMPONENT_STATES):
        "Sets the state of the action row buttons to a new state"
        if new_state == previous_state:
            return
        action_row: discord.ui.ActionRow = self.segments[component_key]['action_row']
        section : discord.ui.Section = self.segments[component_key]['section']
        old_button = action_row.children[0]
        action_row.remove_item(old_button)
        match new_state:
            case 'enabled':
                
                if previous_state != 'inexistent':
                    
                    edit_button = action_row.children[0]
                    #remove the disable button, replace it with enable button and then reinsert the edit button to maintain order.
                    action_row.remove_item(edit_button)
                    if isinstance(edit_button, OpenConfigViewButton):
                        cfg = edit_button.cfg
                    else: raise Exception("Somehow it's not a OpenConfigViewButton, which is not meant to happen there.")
                    
                else:
                    cfg = await self.engine.get_single_config(str(self.guild.id), component_key)
                    if not cfg: raise Exception("Unable to obtain config")
                    edit_button = OpenConfigViewButton(self, "Edit",cfg, self.engine)

                new_button = DisableButton(component_key, self, self.engine) ; new_button.id = old_button.id
                action_row.add_item(new_button).add_item(
                    edit_button
                )
                    
            case 'disabled':
                if previous_state != 'inexistent':
                    
                    edit_button = action_row.children[0]
                    #remove the disable button, replace it with enable button and then reinsert the edit button to maintain order.
                    action_row.remove_item(edit_button)
                    if isinstance(edit_button, OpenConfigViewButton):
                        cfg = edit_button.cfg
                    else: raise Exception("Somehow it's not a OpenConfigViewButton, which is not meant to happen there.")
                    
                else:
                    cfg = await self.engine.get_single_config(str(self.guild.id), component_key)
                    if not cfg: raise Exception("Unable to obtain config")
                    edit_button = OpenConfigViewButton(self, "Edit",cfg, self.engine)

                new_button = EnableButton(component_key, self, self.engine) ; new_button.id = old_button.id
                action_row.add_item(new_button).add_item(
                    edit_button
                )
                    
            case 'inexistent':
                cfg = None
                edit_button = action_row.children[0]
                action_row.remove_item(edit_button)
                # Replace the 2 buttons with a Create button
                new_button = CreateConfigViewButton(self, "Create", str(self.guild.id),component_key, self.engine)
                action_row.add_item(new_button)
                    
        # remove old section text with the updated one
        section.remove_item(section.children[0]).add_item(
            discord.ui.TextDisplay((
                f"## {component_key.replace('_', ' ').capitalize()}\n"
                f"Logging channel: {f"<#{cfg.logging_channel}>" if (cfg and cfg.logging_channel) else "`None`"}\n"
                f"Status: {self.STATE_MAP[new_state]}"
            ))
        )

    def create_segment(self, component_tuple: tuple[str, BaseAutomodComponentConfig | None], state: COMPONENT_STATES):
        """A segment consists of a section and an actionrow of buttons right below"""
        component_key = component_tuple[0]
        cfg = component_tuple[1]
        
        section = discord.ui.Section( # Channel and roles
            discord.ui.TextDisplay((
                f"## {component_key.replace('_', ' ').capitalize()}\n"
                f"Logging channel: {f"<#{cfg.logging_channel}>" if (cfg and cfg.logging_channel) else "`None`"}\n"
                f"Status: {self.STATE_MAP[state]}"       
            )),
            accessory=discord.ui.Button(label = "Placeholder"), # placeholder until i get img links for the thumbnail
        )

        match state:
            case 'enabled':
                if cfg:
                    disable_button = DisableButton(component_key, self, self.engine)
                    disable_button.id = self.ID_increment + 1
                    edit_button = OpenConfigViewButton(self, "Edit", cfg ,self.engine)
                    edit_button.id = self.ID_increment + 2
                    action_row = discord.ui.ActionRow(disable_button, edit_button)
                    self.ID_increment += 10
                    #print("Disable button: ",disable_button)

                else:
                    raise Exception("Lowkey i have no clue how this happened")
                    
            case 'disabled':
                if cfg:
                    enable_button = EnableButton(component_key, self, self.engine)
                    enable_button.id = self.ID_increment + 1 
                    edit_button = OpenConfigViewButton(self, "Edit", cfg ,self.engine)
                    edit_button.id = self.ID_increment + 2
                    action_row = discord.ui.ActionRow(enable_button, edit_button)
                    self.ID_increment += 10
                    #print("Enable button: ",enable_button)
                else:
                    raise Exception("Lowkey i have no clue how this happened")
            case 'inexistent':
                create_button = CreateConfigViewButton(self, "Create", str(self.guild.id), component_key, self.engine)
                create_button.id = self.ID_increment + 1
                self.ID_increment += 10
                #print("Create button: ",create_button)
                action_row = discord.ui.ActionRow(create_button)


        segment = {
            "section" : section,
            "action_row" : action_row
        }
        return segment

    def init_guild_segments(self):
        ""
        from config import ENGINE_CONFIG
        
        comp_dict: dict[str, BaseAutomodComponentConfig] = {}
        for c in self.config_list:
            comp_dict[c.COMPONENT_KEY] = c
        # 1. Traverse through ALL the components the automod supports
        for component_key in ENGINE_CONFIG['components']:
            # Check if the guild already set this one
            if component_key in comp_dict:
                # Then we check if enabled or disabled
                config = comp_dict[component_key]
                if config.enabled:
                    s = self.create_segment((config.COMPONENT_KEY, config), 'enabled')


                else:
                    s = self.create_segment((config.COMPONENT_KEY, config), 'disabled')

            else:
                # It doesn't exist
                s = self.create_segment((component_key, None), 'inexistent')

            self.segments[component_key] = s

    def build_container(self) -> discord.ui.Container:
        component_title = (
            "Master Automod Control Panel"
        )
        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# {component_title}\n"
                f"**Guild ID:** `{self.guild.id}`"
            ),
            self.panel_state_display,
            accent_colour=0xCBD4DE
        )
        for key, segment in self.segments.items():
            container.add_item(discord.ui.Separator())

            container.add_item(segment['section'])
            container.add_item(segment['action_row'])

            container.add_item(discord.ui.Separator())

        return container

    def refresh_display(self) -> None:
        pass

    def get_automod_config_view(self, config: BaseAutomodComponentConfig, engine: AutomodEngine, 
                                author_id: int, guild: discord.Guild,) -> AutomodComponentConfigPanelView:
        automod_panel = AutomodComponentConfigPanelView(config, engine, author_id, guild)
        automod_panel.master_panel = self
        return automod_panel

    def finish(self, status: str) -> None:
        self.refresh_display()

        for key, segment in self.segments.items():
            action_row: discord.ui.ActionRow = segment['action_row']
            for button in action_row.walk_children():
                if isinstance(button, discord.ui.Button):
                    button.disabled = True
        self.stop()




class AutomodLogView(discord.ui.LayoutView):
    """Interactive embed that displays information of action(s) taken by the automod."""

    def __init__(self, automod_log: AutomodLog) -> None:
        super().__init__(timeout=86400)
        self.log_data = automod_log
        self.timeout_checked = False # Niche attribute used by the timeout button to handle cases where a timeout expired/was removed

        # Format the data
        self.prepare_text()

        # Build the container
        self.container = self.build_container()

        # Action row containing the buttons
        self.button_row = self.build_button_row()

        self.add_item(
            self.container
        ).add_item(
            self.button_row
        )

    def prepare_text(self):
        "Formats the log data into text to be added to the embed."
        
        log_channel = self.log_data.log_channel
        if not log_channel:
            print("No log channel was set.")
            return 

        user = self.log_data.message_object.author
        message = self.log_data.message_object
        channel = message.channel
        
        if isinstance(channel, (discord.DMChannel, discord.GroupChannel)):
            raise Exception("DM or Group channel got somehow flagged? wth")

        has_attachments = "✅" if message.attachments else "❌"
        has_sticker = "✅" if message.stickers else "❌"

        extra_info = ""
        if has_attachments:
            extra_info += "Message has attachments\n"
        elif has_sticker:
            extra_info += "Message has stickers\n"

        self.header_txt = discord.ui.TextDisplay(f"# AUTOMOD LOG")

        self.body_general = discord.ui.TextDisplay((
            f"Reason: {self.log_data.reason}\n"
            f"User: <@{user.id}> - `{user.name}`\n"
            f"In: {channel.mention}\n"
        ))

        self.additional_info = discord.ui.TextDisplay(
            f"Has Attachments: {has_attachments} | Has Sticker: {has_sticker}"
        )

        self.flagged_msg_text = discord.ui.TextDisplay(f"### Flagged Message:\n> {message.content}")

        self.delete_text = discord.ui.TextDisplay(
            f"Message Deleted: ❌"
        )
        self.dm_text = discord.ui.TextDisplay(
            f"DM'd: ❌"
        )
        self.verbal_text = discord.ui.TextDisplay(
            f"Verbal Messaged: ❌"
        )
        self.timeout_text = discord.ui.TextDisplay(
            f"Timedout: ❌"
        )

        delete_action = self.log_data.delete_success[1]
        dm_action = self.log_data.dm_success[1]
        verbal_action = self.log_data.message_success[1]
        timeout_action = self.log_data.timeout_success[1]

        if self.log_data.delete_success[0] and delete_action:
            self.delete_text.content = (
                f"Message Deleted: ✅"
            )

        if self.log_data.dm_success[0] and dm_action:
            self.dm_text.content = (
                f"DM'd: ✅"
            )

        if self.log_data.message_success[0] and verbal_action:
            self.verbal_text.content = (
                f"Verbal Messaged: ✅"
            )

        if self.log_data.timeout_success[0] and timeout_action:
            self.timeout_text.content = (
                f"Timed out: ✅ - Duration: {timeout_action.duration} minutes."
            )

    def build_container(self) -> discord.ui.Container:
        Separator = discord.ui.Separator
        self.moderator_action = discord.ui.TextDisplay("Moderator Action: `None`")
        container = discord.ui.Container(
            self.header_txt,
            Separator(),
            self.body_general,
            Separator(),
            self.additional_info,
            Separator(),
            self.flagged_msg_text,
            Separator(),
            self.delete_text,
            self.dm_text,
            self.verbal_text,
            self.timeout_text,
            Separator(),
            self.moderator_action
        )

        return container

    def build_button_row(self) -> discord.ui.ActionRow:
        user = self.log_data.message_object.author
        if isinstance(user, discord.Member):

            self.acknowledge_button = AcknowledgeButton()
            self.acknowledge_button.panel = self

            self.send_dm_button = SendDMButton(user)
            self.send_dm_button.panel = self

            self.remove_timeout_button = HandleTimeoutButton(user, self.log_data.timeout_success[0])
            self.remove_timeout_button.panel = self

            action_row = discord.ui.ActionRow(
                self.acknowledge_button,
                self.send_dm_button,
                self.remove_timeout_button
            )

        else:
            return discord.ui.ActionRow()

        return action_row

    def finish(self, action_done_text: str) -> None:
        self.moderator_action.content = f"Moderator Action: {action_done_text}"

        for button in self.button_row.walk_children():
            if isinstance(button, discord.ui.Button):
                button.disabled = True
        self.stop()