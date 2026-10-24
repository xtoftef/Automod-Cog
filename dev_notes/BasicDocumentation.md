# Introduction

This file is a brief walkthrough of the system for the automod cog so far. I will begin with important notes, and running instructions, then further down will explain things about the architecture and the various files and classes.

# ⚠️WARNING: This file is currently partially outdated and needs review. So take any notes there lightly or double check with the current state of the codebase.⚠️

## Running instructions

First of all, dependencies. Make sure you downloaded the discord.py library, which is the main thing we need.

The file you will want to run is `bot.py`. At the top of it, `TEST = True` makes the bot use the test bot's token, and `TEST = False` the production one. You need the matching token available as an environment variable, e.g. in a .env file in the workspace:
```env
TEST_BOT_TOKEN = <test_token_here>
PRODUCTION_BOT_TOKEN = <production_token_here>
```
Without the token, the bot won't run. NOTE: `bot.py` doesn't load the .env file by itself, so set up your IDE's run configuration to load it (PyCharm and VS Code both can).
As for the various things like the JSON file, logging files and stuff, the program will handle those on its own, so don't worry about that.

## Development notes

To be honest, the workspace is not quite ready for proper taking over and multi-dev development. The architecture is in a stable state, meaning most of the features work without breaking (albeit there's fine-tuning required). However, it will take some time to go over the system and understand how it works. My main goal was to reduce the amount of work needed overall when you try to implement a new automod component. Basically, the engine and cog should remain untouched assuming you add a new component. 

Therefore, you'll find useful to know which files you want to work on if trying to implement an automod component. 
As far as I remember, this is what you should do:
- To implement a new component, create its own file in [src/automod_components/](/src/automod_components/). You'll want to implement the following: `BaseAutomodComponentConfig`, `BaseAutomodComponent` and `BaseChannelManager`. You might find useful to use the existing components ([image_rate_limiter.py](/src/automod_components/image_rate_limiter.py), [chain_prevention.py](/src/automod_components/chain_prevention.py)) as a reference. Also override `RESPONSE_PLACEHOLDERS` on your config so the general modal shows the right placeholders, and use `safe_format` from [utils.py](/utils.py) in `format_response` so a bad admin template can't break the automod. When your automod flags a message, return the actions the bot should take (see `AutomodResponse` below). The step-by-step guide with a skeleton is in the [CHANGELOG](/CHANGELOG.md#how-to-add-a-new-automod-feature). 
- Once the component's backend is done, you only need to to head to [modals.py](/DiscordUI/modals.py) to implement the specific modal for your component's unique settings. 
- Lastly, a bunch of the classes require a sort of dictionary that maps a config key to the respective component or its config. You'll need to manually add your component to these. This is something I'm planning to change so that you only need to add the component to one place once it's ready, but for now this is how it is. Here are some quick links to where to find them:
    - `__all__` modification in [modals.py](/DiscordUI/modals.py#L1). Just add your modal class to the dunder all.
    - `unique_modal_router` add your modal class to the match-case ladder. [modals.py](/DiscordUI/modals.py). Use a class pattern with parentheses (`case YourConfig():`). A bare name (`case YourConfig:`) is a capture pattern that matches everything and makes the file fail to import once there's more than one case.
    - `AVAILABLE_COMPONENTS`. Head to [automod_engine.py](/src/automod_engine.py). Add your component there (you might need to add it to the imports on top)
    - `from_config` Add your component class to the router in `BaseAutomodComponent.from_config`. [automod_models.py](/src/automod_models.py). Add it before the final `raise`.
    - `CONFIG_MAP` Add your config class to the dictionary/map. [memory_manager_implementations.py](/src/memory_manager_implementations.py)
    - `CONFIG_REGISTRY` Add your config class to the dictionary. [automod_cog.py](/automod_cog.py). Without it, `/config-add` rejects your component.

# About the architecture

The architecture has a good flow, first we need to understand that the Discord bot is simply just an interface for the user to communicate with the bot. Similar to how HTML is the interface that allows interaction with the backend. 

## bot.py
So, first of all, the bot's endpoint is [bot.py](/bot.py). This is where we will add our cogs and some basic bot config. You'll see we are adding a cog known as AutomodCog. This cog is pretty much the root from which we can trace the different functionalities and components of the bot. Therefore, you'll want to head to [Automod](/automod_cog.py) to see the different components and commands we added to the bot. 

## automod_cog.py
Once you are in [automod_cog.py](/automod_cog.py), you'll see that the cog consists of 3 important components in the constructor:
```py
class AutomodCog(commands.Cog):
    "you can implement the commands and logic here, it also still supports the on_message function."

    def __init__(self, bot: commands.Bot, memory : BaseAutomodMemoryManager = DEFAULT_MEMORY ) -> None:
        super().__init__()
        self.bot = bot 
        self.automod_engine = AutomodEngine(memory, [])
```
`bot` simply is the bot endpoint client that we have, that will be used to communicate with the discord servers the bot is in. Simple enough.
`memory` is also an important parameter, but the cog never interacts directly with the memory, you'll notice that there is no `self.memory` which is a design choice where we won't allow the cog to interact directly with the memory/storage, instead it interacts with the memory through the engine. NOTE: By memory, i mean the persistent memory/storage, currently the data is stored in a JSON file.
`automod_engine` is our next point of interest, as you see, we initialize the engine with the memory implementation of our choice (currently JSON). You will also notice that I pass an empty list where I should have passed a list of guilds that the bot is part of. This is just a small workaround for an issue that I faced where the cog was initialized before the client got properly connected, which returned an empty list. This might need to be changed in the future, but the soft fix was to assign the correct list of guilds in [bot.py](/bot.py) within the `on_ready` function and then trigger the initialization command once again. Basically, all this is to ensure that the bot enables all the automods when it goes online. With this covered, I will explain how the engine works in a section below, so don't worry if you don't understand its purpose very well yet.

### `on_message` method
This is a crucial method that basically handles the messages that the bot receives. The current implementation only receives the message and forwards it to the automod_engine (our backend) to handle. It's pretty clear and simple, so there's not much to explain.

### Commands
Before I cover the commands, it's important to understand what **config** and **component** means in this context. Within the scope of the automod engine, config will most likely refer to an automod component's config settings. This can be modified by the server admins. An automod component is kind of like a dedicated worker. Similar to how you have bots that have one part or component that handles banned words, another that handles links, another that handles emoji limit per message. 
Below are some commands that the bot has:
- `view-config`: This command allows an admin to view the server's config for a particular automod component.
- `add-config` : This command allows an admin to add an automod component to the server IF it does not exist already.
- `update-config`: This command allows an admin to update an automod component's config settings IF it exists.

BONUS:
There's also a `dummy-config-view` command that's to be used purely for testing. I used this for testing the modals and views for discord. This can be modified as much as you want without breaking the other commands.


# automod_engine.py
Heading to [automod_engine.py](/automod_engine.py).
Now, this is essentially the heart of the entire system. The whole bot relies on this to function as intended. The engine does the following:
- Keep all of the active automods for each server in a cache
- processes the messages by routing them to the automod component assigned to a specific server. (It essentially just doesn't handle the messag processing itself, it routes it to the dedicated experts that need to process that message and return a conclusion). Now, it can happen that a message flags multiple automods, in that event, I believe it's just the first come first served rule that happens. Though in the future, I might add an automod component priority system, which basically will work about the same way, except we reorder the responses in terms of priority and take the first positive flag.
- Interacts directly with the memory manager to retrieve data and also add/update data to the persistent memory.

```py
class AutomodEngine():
    AVAILABLE_COMPONENTS : tuple = (
        ImageRateLimiterComponent.CONFIG_KEY,
    )

    "Manager of all the automod components for all guilds"
    def __init__(self, memory:BaseAutomodMemoryManager, guilds: list[Guild]) -> None:
        self.memory = memory
        self.guilds = guilds
        print("Guilds:", guilds)
        self.cache : dict[str, dict[str,BaseAutomodComponent]] = {
            # guild_id -> dict of components (Config_key -> component object)
        }
        self.init_all_guilds_automod()
```
The `AVAILABLE_COMPONENTS` tuple is basically a record of which component implementations the engine supports. More on this later.
You'll notice that we have a `self.cache` attribute, this basically holds all the automod components that are active and running and can process messages. Grouped by their respective guilds ofc.
It might seem very foreign for now, since I need to explain more on the components, configs and base classes, which I will cover shortly.

But essentially, think of the engine has a massive router that routes messages to the concerned automod components and is the bridge between the interface, storage/memory and processing. It's the crossroad of the system.

# automod_models.py

Heading to [automod_models.py](/automod_models.py).
This is yet another CRUCIAL file for the system. It's essentially the file that keeps the different templates for the backend. The only templates that are not included in there are the DiscordUI related ones (such as modals, etc.)
This file contains a bunch of dataclasses, abstract classes and other useful variables relevant for type checking.
Below are important classes that currently exists in that file:
- `AutomodResponse` - Dataclass
- `BaseAutomodComponentConfig` - Abstract Dataclass
- `BaseAutomodComponent` - Abstract class
- `BaseChannelManager` - Abstract class
- `BaseAutomodMemoryManager` - Abstract class

## `AutomodResponse`
This is basically a small wrapper for the response that the engine returns to the bot. It holds `flagged` (whether the message tripped the automod), `reason` (a short explanation, useful for logs) and `actions`, the list of things the bot should do about it, or `None`. The bot runs the actions in order in `_handle_automod_response` ([automod_cog.py](/automod_cog.py)). Each one runs on its own, so a failed DM doesn't stop the delete.

The available actions (all subclasses of `BotAction`):
- `DeleteAction()` deletes the flagged message.
- `MessageAction(text)` posts a message in the channel, deleted after 5 seconds.
- `DMAction(text)` DMs the member.
- `TimeoutAction(minutes, reason)` times the member out.

To add a new kind of action, add a `BotAction` subclass in [automod_models.py](/src/automod_models.py) and handle its `action_type` in `_handle_automod_response`. 

## `BaseAutomodComponentConfig`
This is an abstract dataclass that specific configs will inherit/implement. The idea is that most automods have paramaters/configurations that are in common, such as affected channels, ignored roles or a particular response. This base class is intended to handle all of these so that the specific implementations of the automod only need to worry about their own specific settings.
IMPORTANT NOTE: Any implementation should implement the abstract classes found in the dataclass. They should also override `CONFIG_KEY` with a uniquely identifiable key string associated to a particular automod.

## `BaseAutomodComponent`
This is an abstract class that specific automod components will implement. The config dataclass is just to hold the data, it doesn't do any sort of processing or management other than really basic data convertion and convenience methods. 
```py
class BaseAutomodComponent(ABC, Generic[ManagerT, ConfigT]):
    "Base class from which all automod components will inherit"

    CONFIG_KEY: ClassVar[str] = ""

    def __init__(
        self,
        config: ConfigT,
        guild: Guild,
        memory: BaseAutomodMemoryManager,
    ) -> None:
        super().__init__()
        self.config = config
        self.memory = memory
        self.channels: dict[str, ManagerT] = {}
        self.initialize_channel_helpers(guild)
        if not self._config_key_matches():
            raise NotImplementedError((f"Config Key mismatch detected.\nComponent key: {self.CONFIG_KEY}"
                                       f"\nPassed Config key: {self.config.CONFIG_KEY}\nMake sure you implemented the automod component properly."))
```
`config` and `memory` are clear enough on their own, I will be explaining the memory base class later on.
`channels` is the important part there. Basically, each channel would have its own individual counter in a way. Like, if you send a message in channel X, you don't necessarily want another message that is sent in Y to get flagged. Particularly if automods have a scope that affects all members (like, the counter is per channel and not per member). Therefore, there's a manager for each channel, which is what this dictionary does. I'll go over what the managers do later on.

IMPORTANT: You'll see there's a `CONFIG_KEY` class variable. Any implementation of the automod should share the same config key as the config dataclass implementation. 

## `BaseChannelManager`
Technically, it's not a complicated class to understand. This is an abstract class that all the specific channel manager implementations associated to their respective automod component must inherit from. The channel manager is the actual logic/algorithm that determines whether a message flags the automod or not. They don't care where the message came from, they only keep track of the state of the automod and whether or not an incoming message violates the criteria.

The exact methods that you will need to implement that class is up to you, since different automods will have different criteria.

## `BaseAutomodMemoryManager`
This is an abstract class that defines methods that the engine will call to interact with the persistent storage. Whether you use a JSON based storage or a database, the engine does not care. That's the advantage of this abstract class. Currently there's only a JSON implementation, but later on we might move to a database, and the migration will not require any change to the engine's logic. 
For the most part, it's only concerned about accessing/modifying the data of the various servers and their respective automods settings. 

# automod_components/
Heading to [automod_components](/src/automod_components/)
This folder holds the automod implementations, one file per component:
- [image_rate_limiter.py](/src/automod_components/image_rate_limiter.py): allows only X image messages within a window of Y messages, per channel.
- [chain_prevention.py](/src/automod_components/chain_prevention.py): flags a media message (attachment, embed or sticker) that extends a reply chain of media messages past `max_chain_length`. Several replies to the same message are separate chains, and text messages break a chain. Media messages are forgotten after `duration` seconds. Members with an ignored role are never flagged but still count as chain links.

The router that turns a saved config into the right component (`from_config`) lives in `BaseAutomodComponent` in [automod_models.py](/src/automod_models.py).

NOTE: Before this layout, all components lived in a single `src/component_implementations.py`. That file has been removed; it's still in the git history if you need it. 

# memory_manager_implementations.py

Heading to [memory_manager_implementations.py](/src/memory_manager_implementations.py)
This file contains all the implementations of the BaseAutomodMemoryManager class. Currently only a JSON implementation.

# Discord UI
You will also notice a folder [DiscordUI](/DiscordUI/). This folder contains all the files relevant for Discord UI stuff, namely using Discord's API ComponentsV2. This includes things like layout views, modals (Discord's forms), buttons, dropdown and all that good UI stuff. Though, ComponentsV2 has some formats that must be respected, so i strongly recommend checking the documentation about it both for discord.py's wrapper and Discord's API reference.


Which is why you'll see a folder known as . This folder contains