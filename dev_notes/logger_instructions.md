
# Quick Guide: Adding Logging to a New Module

This guide explains how to add logging to a new file in your project using the established `logger.py` setup, ensuring logs are properly scoped under the `automod` namespace.

---

## Step 1: Import and Create the Logger

At the top of your new file (e.g., `src/automod_components/new_feature.py`), import `get_logger` from `logger.py` and create a module-level logger instance.

```python
# src/automod_components/new_feature.py

from logger import get_logger

# Define a child logger under the "automod" namespace.
# Best practice: use dot notation representing the file location.
logger = get_logger("components.new_feature")

```

---

## Step 2: Choose the Correct Log Level inside Functions

Use the appropriate log level based on what the event represents:

| Log Level | Purpose | Example Use Case |
| --- | --- | --- |
| `logger.debug()` | Verbose state dumps and step-by-step logic | Dict/dataclass dumps, local variable checks, loop evaluations. *(Hidden in Production)* |
| `logger.info()` | Key lifecycle events and success milestones | Initializing a component, saving data, processing completed. |
| `logger.warning()` | Expected non-fatal issues or business failures | Rate limit hit, feature disabled for guild, missing optional settings. |
| `logger.error()` | Exceptions or unexpected runtime errors | Failed database writes, broken API calls. Include `exc_info=True` to print tracebacks. |

---

## Step 3: Practical Code Examples

### 1. In Class Methods & standard Functions

Always pass arguments directly into loggers using **`%s` format specifiers** rather than f-strings. This allows Python to skip string formatting entirely when the log level is disabled (e.g., `DEBUG` logs in production).

```python
class NewFeatureComponent:
    def __init__(self, config):
        self.config = config
        # INFO: Major initialization event
        logger.info("Initializing NewFeatureComponent for Guild ID: %s", config.guild_id)

    async def process_data(self, user_id: int, payload: dict) -> bool:
        # DEBUG: Low-level input payload trace
        logger.debug("Processing payload for user %s: %s", user_id, payload)

        if not self.config.enabled:
            # WARNING: Normal business guardrail
            logger.warning("Skipping execution: NewFeature is disabled for Guild %s", self.config.guild_id)
            return False

        # ... process logic ...

        # INFO: Operation succeeded
        logger.info("Successfully processed payload for user %s", user_id)
        return True

```

### 2. In `try / except` Error Blocks

Pass `exc_info=True` in `logger.error()` to automatically attach full error stack traces when debugging:

```python
async def save_user_data(self, data: dict):
    try:
        await self.memory.save(data)
        logger.debug("Saved data payload: %s", data)
    except Exception as e:
        # ERROR: Captures the error message AND prints the full traceback if IS_DEV is active
        logger.error("Failed to save user data due to an error: %s", e, exc_info=True)

```

---

## Step 4: Output Example

When running in `DEBUG` mode (`IS_DEV = True`), your output across files will automatically format consistently:

```text
2026-10-29 18:35:00 | INFO     | automod.components.new_feature | Initializing NewFeatureComponent for Guild ID: 123456789
2026-10-29 18:35:01 | DEBUG    | automod.components.new_feature | Processing payload for user 987654321: {'key': 'value'}
2026-10-29 18:35:01 | WARNING  | automod.components.new_feature | Skipping execution: NewFeature is disabled for Guild 123456789

```

