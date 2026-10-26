# Changelog

### LAST UPDATE DATE: 24/10/2026

## Brief summary

This most recent commit addresses includes important changes/improvements to the architecture. The goal of these changes was to improve the developer's experience of implementing and mainly integrating new components within the cog. Previously, automod component classes were loosely tied, requiring some router functions that required manually adding classes and tiers to an if-else ladder or match-case(switch-case) ladder. This new change actually kills this need and simplifies router functions. 
The introduction of [config.py](/config.py) now centralizes all the parts/classes of a specific component within one dictionary that serves as a very convenient wrapper. `ENGINE_CONFIG` is the dictionary that must be modified and allows people to enable or disable components **across the entire cog's scope**, which hides the components entirely from discord servers if they are disabled. 

The other addition was a `open-master-config` command to the automod cog. This basically opens a master config control panel within the guild that allows its admins to create new configs, enable/disable them or modify them. This essentially gives a more user friendly experience as things are more centralized and reduces the need to even use commands like `config-add` or `config-update`.

## Details on the new Architecture

This section of the file will go a bit more in depth when it comes to what the new architecture does and how it works. 
First of all, this file does not really change more Discord bot/client related aspects (such as token, intents, cogs, etc.). It's the master config for the **COG** and not the bot gateway itself. 
With this out of the way, the file [config.py](/config.py) file can be loosely segmented into distinct parts (though this might need a clean up later on):
- TypedDict classes definitions. I considered typed dictionaries to be really useful for this as a way to ensure valid data is passed to the automod. It also serves as a loose template for what classes are to be implemented for a new component to function.
- Declaring variables and the dictionaries. This is kind of the developer's control panel for the cog, allowing the developer to fine tune a few things here and there.
- Useful functions. These are really important or provide good use.

I won't go through all of them in detail, just the crucial parts.

### ENGINE_CONFIG dictionary

Currently, this is just a dictionary of components, but it might expand in the future.
```py
class EngineConfigDict(TypedDict):
    components : dict[str,ComponentDict]

class ComponentDict(TypedDict):
    activate : bool
    config_type : type[BaseAutomodComponentConfig]
    component_type : type[BaseAutomodComponent]
    modal_type : type[BaseComponentSpecificModal]
```
The interesting part there is the ComponentDict. This dictionary is our loose template as to what counts as a valid component. It's your checklist to know if you implemented every class you need for your component to be added to the automod. Though you must note that this doesn't mean the component will end up working as intended, it's more of a type safety net, not a logic safety net. If ever components end up having a new base class that needs to be implemented, it will be added to this dictionary as well.
The `activate` field simply determines whether or not the component will be added to the automod as something that server admins can add. The idea was to be able to add and remove components from the cog without having to go and remove it everywhere. Just change one line and you're good to go.
What's important to note is that I did a major change to the Base Component classes where they now basically all need a `COMPONENT_KEY` (formerly `CONFIG_KEY` in the config). This key is the foundation of the router that was implemented. The dictionary MUST be set in such a way that the component classes must have the same shared component key and the key within the dictionary is the same as the COMPONENT_KEY attribute in the classes.

### Useful functions
- `get_component_related_class()`: This is now our primary router function, which simply fetches the class type depending on the component key passed and the desired component part class type we want. 
- `verify_key_matching()`: Checks if the keys of the components added to the dictionary are matching with each other. Raises an error if there's a single mismatch between component parts/classes that SHOULD be matching. Currently not really used, but is ready to be implemented in the system more deeply later on.

### COG_CONFIG

Not a big dictionary. It just holds data about the memory manager we'll use and then the engine config (though it technically doesn't really need the engine config as of now, since the ENGINE CONFIG is used directly by the different files WITHOUT going through COG_CONFIG, but that's currently not a big issue). The only thing that it does mainly is the memory manager part. 
In the future, this dictionary might be expanded or modified to become a bit more meaningful and defining for the behavior of the system. For now, just fundamental stuff.

## `open-master-panel` command
This one is a big one that required modifying a lot of files, primarily within the DiscordUI folder. There are too many changes to explain all of them in one go under one section, so I'll list the specific changes as I walk through all the modifies code files.

# Modified files:
## [automod_cog.py](/automod_cog.py)
- Removed the CONFIG_REGISTRY constant since it is not relevant with the new architecture.
- Removed an old TODO note/comment.
- Updated the autocomplete methods to work with the new centralized components architecture. Also added a flag that only suggests automods that are labeled as activated.
- added `open_master_panel` method/command. Simply returns an interactive layout view to manage a guild's automod components.
- added `app_commands.guild_only` decorators over most commands.
- Modified most commands so that they defer an interaction as soon as it comes and later edits the message when the request is processed.
- Added two commands `check-engine-cache` and `check-automod-cache`. The first simple returns a simple string in JSON format containing some data about what's currently in the engine's cache. The latter returns a simple JSON string that gives insight about what components are active and what channels are currently observed.
- Removed the body for `dummy_config` command, meaning it does not work anymore. Might be removed entirely in the future or repurposed.
- `_send_automod_log` method now sends an interactive `AutomodLogView` instead of a raw string.

## [bot.py](/bot.py)
- `TEST` constant now comes from [config.py](/config.py)
- AutomodCog object is now initialized with the memory config in [config.py](/config.py) under `COG_CONFIG`.

## [config.py](/config.py)
- New file entirely, which was briefly explained [above](#details-on-the-new-architecture).

## [buttons.py](/DiscordUI/buttons.py)
- Modified `SaveConfigButton` class:
    - Renamed from `SaveDummyConfigButton` to `SaveConfigButton`. For obvious reasons.
    - Added an if block to handle the new `MasterPanelView` in the event where a `AutomodComponentConfigPanelView` was created following the master panel.
    - added `_write_master_edit_cfg` method to handle the event when a config is created. Otherwise the master panel does not update correctly when a user creates a new config and saves it.
- Modified `CancelConfigButton` class:
    - Renamed from `CancelDummyConfigButton` to `CancelConfigButton`. For obvious reasons.
    - Added an if block to handle the new `MasterPanelView` in the event where a `AutomodComponentConfigPanelView` was created following the master panel.
- Added a `EnableButton` class. This allows a user to enable a disabled component within the master panel.
- Added a `DisableButton` class. This allows a user to disable an enabled component within the master panel.
- Added an `OpenConfigViewButton` class. Which triggers a `AutomodComponentConfigPanelView` when pressed.
- Added a `CreateConfigViewButton` class. It inherits from the class above, except it's fine-tuned to handle the event where a config does not exist yet and allows the user to create one.
- Added a `SendDMButton` class. Designed to work with `AutomodLogView`. Opens a modal that sends a DM when pressed.
- Added a `AcknowledgeButton` class. Designed to work with `AutomodLogView`. Opens a modal that prompts for a reason and marks the automod log as reviewed.
- Added a `HandleTimeoutButton` class. Designed to work with `AutomodLogView`. Opens a modal that allows the moderator to add/remove a timeout from a user.

## [modals.py](/DiscordUI/modals.py)
- Added `COMPONENT_KEY` variables under `BaseComponentSpecificModal` class and its children.
- Modified `unique_modal_router` to use the new method `get_component_related_class` from `config.py`.
- Added a `DMInputModal` class. Designed to work with `AutomodLogView`.
- Added a `CommentInputModal` class. Designed to work with `AutomodLogView`.
- Added a `TimeoutHandlerModal` class. Designed to work with `AutomodLogView`.
- Modified `EditChannelsAndRolesModal`. 
    - Added an input field for logging channel and the relevant handling for updating the data.

## [views.py](/DiscordUI/views.py)
- Minor modifications to `AutomodComponentConfigPanelView`. 
    - Mostly just refactoring/parity changes for the new architecture. Also added a `master` attribute that defaults to None. This is to handle cases where the config panel was created from a master panel rather from a command.
    - Added display for the logging channel
- Added `MasterPanelView` class. 
    - This is the view that is used within the `open-master-panel` command.
    - Note: This view can be further improved with some small tweaks here and there to improve it. But it's otherwise functional. It could also take some cleanup from unneeded methods and stuff.
    - added display for the logging channel
- Added a `AutomodLogView` class.
    - This is the view that is used within the `_send_automod_log` method in [automod_cog.py](/automod_cog.py)
    - Mainly works with `AutomodLog` dataclass and displays information about an automod flag.

## [automod_engine.py](/src/automod_engine.py)
- Modified `AutomodEngine` class:
    - Removed the `AVAILABLE_COMPONENTS` constant, since it's of no use with the new architecture that's centralized within `config.py`.
    - Added `enable_component` and `disable_component` methods in order for them to be used by the buttons for the master config panel.
    - Added a `get_single_config` method. Used by the master panel, and might be useful overall in the future.

## [automod_models.py](/src/automod_models.py)
- renamed `CONFIG_KEY` to `COMPONENT_KEY`. Refactoring change that makes it more general to component parts rather than a single config.
- Modified `BaseAutomodComponentConfig`. Added an `enabled` attribute that's specific to each guild and marks whether or not a component is enabled or disabled in that guild.
- Modified `BaseAutomodComponent` class.
    - Modified `initialize_channel_helpers` method to cater for the new `enabled` attribute. Basically does not enable any channel helpers if the component is disabled.
    - Modified the `from_config` static method to use the `get_component_related_class` function from `config.py`.
    - Added `__str__` method.

## [memory_manager_implementations.py](/src/memory_manager_implementations.py)
- Modified `JSONMemoryManager`:
    - Removed `CONFIG_MAP` constant given the new architecture now does that job.
    - General parity changes in order to fit the new architecture, using `get_related_component_class` from `config.py`.

## [reply_chain_prevention.py]() / [chain_prevention.py](/src/automod_components/chain_prevention.py)
- renamed the file from `chain_prevention.py` to `reply_chain_prevention.py`
- Renamed the `COMPONENT_KEY` constants value from `chain_prevention_config` to `reply_chain_prevention`
- Modified `ReplyChainPreventionComponentConfig` class:
    - Renamed from `ChainPreventionComponentConfig` to `ReplyChainPreventionComponentConfig`.
    - Parity changes when it comes to the new architecture.
    - parity for the new `enabled` attribute.
- Modified `ReplyChainPreventionComponent`
    - Renamed `ChainPreventionComponent` to `ReplyChainPreventionComponent`.
    - Did a change to the order of the parameters in the constructor. I initially did this to make it simpler for some sort of parity. But I'm realizing that this change could perhaps be undone and the `create` method be added as an abstract class to the base class to force a consistent way of creating a component. This change should perhaps be reviewed and considered in the future.
    
## [image_rate_limiter.py](/src/automod_components/image_rate_limiter.py)
- renamed the `COMPONENT_KEY` constants value from `image_rate_limiter_config` to `image_rate_limiter`.
- Modified `ImageRateLimiterComponentConfig` class:
    - added the `enabled` attribute and related parity changes.
    - Fixed a typo in `to_dict` about the `logging_channel` attribute.
- Modified `ImageRateLimiterComponent`:
    - Did a change to the order of the parameters in the constructor. I initially did this to make it simpler for some sort of parity. But I'm realizing that this change could perhaps be undone and the `create` method be added as an abstract class to the base class to force a consistent way of creating a component. This change should perhaps be reviewed and considered in the future.


