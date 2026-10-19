# Changelog

All notable changes to the Automod Cog are recorded here. Newest changes go on top.

The project targets **Python 3.14** and **discord.py 2.7+**.

---

## 2026-10-20 — Revised merge (branch `revised-merge`)

This merges the **Revised Automod Cog** with `main`. That combines `main`'s bot action system with the chain prevention automod and the bug fixes from the 2026-10-19 update (below), and fixes the problems the merge introduced.

### Added

- **Bot action system** (from `main`). An `AutomodResponse` is now `(flagged, reason, actions)`. A component no longer returns only a message: it returns the list of actions the bot should take.

  | Action | What the bot does |
  |---|---|
  | `DeleteAction()` | Deletes the flagged message |
  | `MessageAction(text)` | Posts `text` in the channel. It is deleted after 5 seconds. |
  | `DMAction(text)` | Sends `text` to the member in DMs |
  | `TimeoutAction(minutes, reason)` | Times the member out. `reason` appears in the audit log. |

  Both automods currently return `[DeleteAction(), MessageAction(<response template>)]` when they flag a message.
- **`/test-automod <msg_id> <action_type>`** (from `main`): runs a single action on a message, to test that the bot has the permissions it needs.

### Changed

- **New folder layout:** each automod component lives in its own file inside [`src/automod_components/`](src/automod_components/):
  - [`image_rate_limiter.py`](src/automod_components/image_rate_limiter.py)
  - [`chain_prevention.py`](src/automod_components/chain_prevention.py)
- **The `from_config` router moved** to `BaseAutomodComponent.from_config` in [`src/automod_models.py`](src/automod_models.py).
- **`src/component_implementations.py` removed.** Its contents now live in `src/automod_components/` and `src/automod_models.py`, and the old file is still in the git history.
- **`bot.py` reads a different token** depending on the `TEST` flag at the top of the file: `TEST_BOT_TOKEN` (when `TEST = True`) or `PRODUCTION_BOT_TOKEN`. It no longer uses `DISCORD_TOKEN`.
- **Actions run independently:** `_handle_automod_response` runs each action on its own. A failing action (DMs closed, missing permission, member outranks the bot) is logged and the remaining actions still run. It returns the list of failed actions, and `/test-automod` now reports those failures instead of always saying "successful".
- Docs ([`dev_notes/BasicDocumentation.md`](dev_notes/BasicDocumentation.md), the README and this changelog) updated for the new layout, the action system and the token variables.

### Fixed

| # | Where | Bug | Effect |
|---|---|---|---|
| 16 | `automod_cog.py` → `on_message` | The merge left a second `engine_process_message(message)` call at the end of `on_message`. | **Every message went through every automod twice.** The image rate limiter counted each image twice, so it flagged at half the configured limit. |
| 17 | `src/automod_models.py` → `process_message` | The merge dropped the line that re-reads `channel_manager` after creating one for a new channel. | A channel created after startup still got "Channel is not watched" for its first message, so the bug #7 fix only half worked. |
| 18 | `automod_cog.py` → `test-automod`, `dummy-config-view` | The test commands had no permission restriction. | **Any member** could make the bot delete messages or time out other members for 60 minutes with `/test-automod`. Both test commands are now admin-only, like the config commands. |
| 19 | `automod_cog.py` → `_handle_automod_response` | Only the delete action handled errors. | A member with DMs closed, or one the bot can't time out, raised an error that stopped the remaining actions from running. |
| 20 | `DiscordUI/views.py` | Bug #13 came back in the merge: the reference to the nonexistent `DummyAutomodEngine`. | Dead code that would raise `NameError`. Removed again. |
| 21 | `README.md` | The merge restored the broken `dev_notes/BasicDocumentation` link (missing `.md`) and lost the changelog link. | Broken link on GitHub. |
| — | `src/automod_models.py` → `initialize_channel_helpers` | Two unused variables were left over from the merge. | No effect. Cleaned up. |

### Known limitations (not changed in this update)

All the limitations listed under 2026-10-19 still apply. In addition:

- **`.env` is not loaded automatically.** `bot.py` only reads environment variables. Either configure your IDE's run configuration to load `.env` (PyCharm and VS Code both can) or add `python-dotenv`.
- **`TimeoutAction` and `DMAction` are not used by any component yet.** They're only reachable through `/test-automod`.
- **`from_config` contains two unreachable lines** after the final `raise`, referring to the old (now removed) `component_implementations.from_config`. They're kept on purpose as a reference and have no effect, but they would fail if ever moved above the `raise`.
- **The `from __future__ import annotations` line was dropped from `DiscordUI/views.py`** in the merge. That's fine on Python 3.14 (the project target), but on 3.13 or older `views.py` fails to import.

---

## 2026-10-19 — Chain prevention + bug fixes

> Paths in this entry are as they were at the time. Since the 2026-10-20 merge, the components live in `src/automod_components/` and `from_config` lives in `src/automod_models.py`.

### Added

- **Chain prevention automod** (`chain_prevention_config`) in its own file, now [`src/automod_components/chain_prevention.py`](src/automod_components/chain_prevention.py).
  - Flags a media message (attachment, embed or sticker) when it extends a **linear reply chain** of media messages past `max_chain_length`.
  - `M1 <- M2 <- M3 <- M4` (each replying to the previous one) with a limit of 3 → **M4 is deleted**.
  - `M2`, `M3`, `M4` all replying to `M1` → separate chains, **nothing is flagged**.
  - Text-only messages are never flagged and **break** a chain they reply to.
  - Members with an ignored role are never flagged, but their messages still count as chain links.
  - Media messages are forgotten after `duration` seconds.
  - Settings: `max_chain_length` (default `3`) and `duration` (default `600` seconds), editable with `/config-add` and `/config-update`.
  - Response placeholders: `{user_id}`, `{max_chain_length}`, `{duration}`.
- `EditChainPreventionSpecificModal` in [`DiscordUI/modals.py`](DiscordUI/modals.py) to edit those settings.
- `safe_format()` in [`utils.py`](utils.py): formats an admin-provided response template and falls back to the default template if it is invalid.
- `RESPONSE_PLACEHOLDERS` class variable on `BaseAutomodComponentConfig`. Each config lists its placeholders, and the "Edit General" modal shows the right ones for each component.
- `BaseAutomodComponent.is_channel_watched()`: the single place that decides whether a channel is covered by a config. It also accounts for categories.
- `OrderedSet.__eq__`, so two configs can be compared with `==`.
- This changelog.

### Changed

- Components can live in their own file instead of all going into `component_implementations.py`.
- `unique_modal_router` now uses class patterns (`case SomeConfig():`) instead of bare names.
- `ImageRateLimiterComponentConfig.format_response` now uses `safe_format`.
- `JSONMemoryManager.save_memory` writes to `<file>.tmp` first and then swaps it in.
- `JSONMemoryManager.sync_get_all_guild_configs` skips a broken or unknown entry (and prints it) instead of raising. The entry stays in the JSON file untouched.
- `.gitignore` now also ignores `guild_data.json.tmp`, `dummy_memory.json` and `dummy_memory.json.tmp`.

### Fixed — bugs that existed before this update

| # | Where | Bug | Effect |
|---|---|---|---|
| 1 | `src/automod_engine.py` → `set_config` | Wrote to `self.cache[guild_id][...]` without creating the guild's entry first. The `KeyError` was swallowed and `False` returned. | `/config-add` silently failed on any server that had no automod yet, which is every new server. |
| 2 | `DiscordUI/buttons.py` → `SaveDummyConfigButton` | Ignored the return value of `set_config`. | The panel showed "✅ Saved" even when saving failed (for example, bug #1). It now shows an error and stays open so the admin can retry. |
| 3 | `src/automod_models.py` → `BaseAutomodComponent.__init__` | `if not self._config_key_matches:` was missing `()`. A method object is always truthy. | The config/component key mismatch check **never ran**. |
| 4 | `DiscordUI/modals.py` → `EditGeneralModal` | The "global" checkbox was created with `default=True` instead of the current value. | Opening "Edit General" on a non-global config and pressing submit quietly turned it back into a global one. |
| 5 | `format_response` (all components) | `str.format_map` on an admin-written template raised on unknown placeholders like `{oops}` or a stray `{`. | The exception happened before the message was deleted, so a bad template **disabled the automod** for that server. |
| 6 | `src/automod_models.py` → `initialize_channel_helpers` | Only a channel's own ID was checked, never its category. | The channel picker allows categories, but selecting one (as affected or ignored) did nothing. |
| 7 | `src/automod_models.py` → `process_message` | Channel managers were only created at startup or on config update. | Channels created after the bot started were **not watched** until someone re-saved the config. They are now picked up on their first message. |
| 8 | `src/memory_manager_implementations.py` → `sync_get_all_guild_configs` | Raised on any unknown or broken entry. | One renamed or removed component, or a hand-edited entry, crashed startup for **every** server. |
| 9 | `src/memory_manager_implementations.py` → `save_memory` | Wrote the JSON file in place. | A crash or power loss mid-write left a half-written file, and the bot then refused to start. |
| 10 | `automod_cog.py` → `on_message` | `message.delete()` errors were not handled. | Missing "Manage Messages" permission, or a message already deleted by a moderator, raised an unhandled error. |
| 11 | `DiscordUI/modals.py` → `unique_modal_router` | `case ImageRateLimiterComponentConfig:` is a **capture pattern** in Python and matches anything. | Adding a second `case` (as the docs instructed) would make the file fail to import with a `SyntaxError`. |
| 12 | `DiscordUI/modals.py` → `EditGeneralModal` | The placeholder hint always listed `{max_images}` and `{window_size}`. | Wrong hint for any component other than the image rate limiter. |
| 13 | `DiscordUI/views.py` | Referenced a `DummyAutomodEngine` class that does not exist. | Would raise a `NameError` if the panel were ever opened without an engine. The dead code was removed. |
| 14 | `DiscordUI/modals.py` | The `TYPE_CHECKING` import used `from views import ...` instead of `from .views import ...`. | Type checkers (PyCharm, Pylance, mypy) couldn't resolve the panel type. |
| 15 | `utils.py` → `OrderedSet` | No `__eq__`. | Two identical configs compared as **not equal**, which would break any future "has anything changed?" check. |

### Known limitations (not changed in this update)

- **Threads and forum posts are not watched.** Messages there come from a `Thread`, which isn't in `VALID_AUTOMOD_CHANNELS`.
- **Link previews may slip past chain prevention.** Discord often attaches a link's embed a moment *after* the message is sent, so a message whose only media is a link preview may not count as a chain link.
- **Automod state is kept only in memory.** Counters and chains reset when the bot restarts. `on_ready` also re-initializes the engine, and it can fire again after a reconnect.
- **A channel moved *out* of a watched category stays watched** until the config is saved again. (Channels moved *into* one are picked up automatically.)
- **First match wins.** If a message trips several automods, the first one in the server's config order decides the response. There is no priority system yet.

---

## How to add a new automod feature

The engine and the cog are built so that a new automod doesn't need changes to their logic. You write one file, then register it in a few places.

Use [`src/automod_components/chain_prevention.py`](src/automod_components/chain_prevention.py) as the reference: it is a complete, self-contained example.

### Step 1 — Create the component file

Create `src/automod_components/<your_feature>.py` with three classes:

| Class | Inherits from | Responsibility |
|---|---|---|
| `YourFeatureComponentConfig` | `BaseAutomodComponentConfig` | Holds the settings (a dataclass). Saved to and loaded from JSON. |
| `YourFeatureChannelManager` | `BaseChannelManager` | The actual detection logic and state for **one channel**. |
| `YourFeatureComponent` | `BaseAutomodComponent[Manager, Config]` | Creates a manager per channel and turns its verdict into an `AutomodResponse` with the actions to take. |

Skeleton:

```py
from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar
from discord import Guild, Message, Member

from src.automod_models import (
    AutomodResponse,
    DeleteAction,
    MessageAction,
    OrderedSet,
    BaseAutomodComponentConfig,
    BaseAutomodMemoryManager,
    BaseAutomodComponent,
    BaseChannelManager
)
from utils import safe_format


@dataclass
class YourFeatureComponentConfig(BaseAutomodComponentConfig):
    "Docstring describing the automod and its settings."

    DEFAULT_MSG_RESPONSE = "<@{user_id}>, ... {your_limit} ..."
    CONFIG_KEY: ClassVar[str] = "your_feature_config"   # unique, must end with "_config"
    RESPONSE_PLACEHOLDERS: ClassVar[tuple[str, ...]] = ("user_id", "your_limit")

    your_limit : int                     # your unique settings
    message_response_template : str

    @classmethod
    def get_default(cls, guild_id: str) -> YourFeatureComponentConfig: ...
    def to_dict(self) -> dict: ...       # include ALL fields, shared and unique
    @classmethod
    def from_dict(cls, config_dict: dict) -> YourFeatureComponentConfig: ...  # raise ValueError on bad input

    def format_response(self, user_id: str) -> str:
        values = {"user_id": user_id, "your_limit": self.your_limit}
        return safe_format(self.message_response_template, values, YourFeatureComponentConfig.DEFAULT_MSG_RESPONSE)

    def format_unique_config_display(self) -> str:
        return f"**Your Limit:** `{self.your_limit}`"   # unique settings only


class YourFeatureChannelManager(BaseChannelManager):
    "State + detection logic for a single channel."
    def __init__(self, channel_id: str, config: YourFeatureComponentConfig):
        super().__init__(channel_id, config)
        self.config: YourFeatureComponentConfig
        # your per-channel state here

    def process_message(self, ...) -> bool:
        "Return True if the message should be blocked."
        ...


class YourFeatureComponent(
    BaseAutomodComponent[YourFeatureChannelManager, YourFeatureComponentConfig]
):
    CONFIG_KEY: ClassVar[str] = YourFeatureComponentConfig.CONFIG_KEY

    def __init__(self, guild: Guild, memory: BaseAutomodMemoryManager,
                 config: YourFeatureComponentConfig | None = None) -> None:
        if config is None:
            config = YourFeatureComponentConfig.get_default(str(guild.id))
        super().__init__(config, guild, memory)

    def add_manager(self, channel_id: str):
        self.channels[channel_id] = YourFeatureChannelManager(str(channel_id), self.config)

    async def _process_valid_message(self, channel_manager: YourFeatureChannelManager,
                                     user: Member, message: Message, is_immune: bool) -> AutomodResponse:
        if is_immune:
            return AutomodResponse(False, "User has an immunity role", None)
        if channel_manager.process_message(...):
            return AutomodResponse(
                True,
                "Short reason, used for logs",
                [
                    DeleteAction(),
                    MessageAction(self.config.format_response(str(user.id)))
                ]
            )
        return AutomodResponse(False, "User did not trigger the automod", None)
```

The shared settings (global mode, affected/ignored channels and categories, ignored roles, response message) and the shared checks (correct guild, watched channel, real member, immunity) are handled by the base classes. You don't write them again.

**Choosing actions:** return whichever actions fit your automod, in the order they should run: `DeleteAction()`, `MessageAction(text)`, `DMAction(text)`, `TimeoutAction(minutes, reason)`. Each one runs on its own, so a failed DM won't stop the delete. If you need a **new kind** of action, add a `BotAction` subclass in `src/automod_models.py` and handle its `action_type` in `_handle_automod_response` in `automod_cog.py`.

### Step 2 — Create the settings modal

In [`DiscordUI/modals.py`](DiscordUI/modals.py), add a `BaseComponentSpecificModal` subclass for your **unique** settings only. Copy `EditChainPreventionSpecificModal` and change the inputs. Always validate the input in `on_submit` and reply with an ephemeral error message if it's invalid.

### Step 3 — Register it (6 places)

| # | File | What to add |
|---|---|---|
| 1 | `src/automod_models.py` → `BaseAutomodComponent.from_config` | Import your config and component **inside the method** (to avoid circular imports) and add an `elif isinstance(config, YourFeatureComponentConfig): return YourFeatureComponent(guild, memory, config)` **before** the final `raise`. |
| 2 | `src/automod_engine.py` → `AVAILABLE_COMPONENTS` | `YourFeatureComponent.CONFIG_KEY` (and the import at the top) |
| 3 | `src/memory_manager_implementations.py` → `CONFIG_MAP` | `YourFeatureComponentConfig.CONFIG_KEY : YourFeatureComponentConfig` |
| 4 | `automod_cog.py` → `CONFIG_REGISTRY` | `YourFeatureComponentConfig.CONFIG_KEY: YourFeatureComponentConfig`. Without it, `/config-add` rejects your component. |
| 5 | `DiscordUI/modals.py` → `__all__` | `"EditYourFeatureSpecificModal"` |
| 6 | `DiscordUI/modals.py` → `unique_modal_router` | `case YourFeatureComponentConfig(): return EditYourFeatureSpecificModal`. **Keep the parentheses** (see bug #11). |

### Step 4 — Test it

1. Set `TEST = True` in `bot.py` and make `TEST_BOT_TOKEN` available to the process (environment variable, or a `.env` loaded by your IDE run configuration). Then run `bot.py`.
2. `/config-add` → pick your component → adjust the settings → **Save**.
3. Check that `guild_data.json` now has your `CONFIG_KEY` under the server's ID.
4. Trigger the automod in a watched channel. Then confirm that a member with an ignored role and an ignored channel are left alone.
5. Use `/test-automod` to check the bot has the permissions each of your actions needs.
6. Restart the bot and check that the automod is still active (it was reloaded from the JSON file).
7. Add an entry for your feature at the top of this changelog.

### Rules that prevent future breakage

- **Never rename a `CONFIG_KEY` once it has been released.** Servers' saved configs are stored under that key. After a rename they are skipped at startup (bug #8 fix) and the servers silently lose that automod.
- **Use `safe_format` in `format_response`.** Server admins write the template, so it can't be trusted to be valid.
- **Make `from_dict` tolerate missing optional fields** (use `.get(key, default)`) when you add a new setting to an existing component. Older saved configs won't have it.
- **Keep detection logic inside the channel manager** and keep the component thin. The manager should not care where the message came from.
- **Return `bool` from `set_config`-style operations and check it in the UI.** Don't report success you didn't verify (bug #2).
- **Commands that can delete messages or punish members must be admin-only** (`@app_commands.default_permissions(administrator=True)`), including test commands (bug #18).
- **When merging by hand, diff the result against both sides.** Bugs #16, #17, #20 and #21 were all introduced or reintroduced by a manual merge.
