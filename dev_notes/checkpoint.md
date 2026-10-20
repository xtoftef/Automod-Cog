This file is mostly just a status check on the automod cog system, I'll simply be going through what has been achieved and what's left to do.

Currently, the system's architecture is rather stable and convenient to work with. Since things do have a nice flow that makes tracing functions and even data a lot simpler. The codebase is basically shaped in such a way that makes it more scalable and easier to debug and even expand, although there is undeniably more work that can be done to improve the architecture.

# What was achieved feature-wise
- A component-based system for the automod. Automod components are basically parts of the automod that handle specific tasks. For example, one component will target reply chains, another banned words, another will rate limit messages. Below are some features shared by all components (but can be fine-tuned per component):
    - Affects channel globally: Whether or not the component will affect all text channels of the guild.
    - User response message: The message that is sent after a user trips the automod. This is basically a template that can be modified in a way that the guild likes.
    - Affected channels: The channels which should be targetted by the automod (if global is false).
    - ignored channels: The channels which should be ignored (if global is True).
    - logging channel: The channel to which the bot will sent a log whenever a user trips the automod.
    - ignored roles: Roles that should be granted immunity from the automod.
- The ability to add and modify component configurations directly from the guild. Server admins can run a command to modify a guild component's config using a user-friendly UI (includes buttons, forms and channel/role selectors).
- Customizable automod actions such as DM'ing the user, deleting the message, timing out the user or simply sending a notification. Though it must be noted that while the system supports this, it is not yet customizable by guilds and are currently only hardcoded in the system.

## Currently existing components
As of now, there are only two component functionalities that were implemented. I will explain them briefly below:
### Image Rate Limiter
This component follows the simple rule of allow **"only X amount of attachments/embeds within a span of Y seconds regardless of who sent it"**. The idea behind this component is to prevent concentrations of attachments/embeds even if separated by a few messages. 

### Reply Chain Prevention
This component follows the following rule: **"Linear reply chains of messages cannot exceed __X length__ assuming that the message at the top of the chain was sent within the last __Y seconds__. This also assumes all messages contain either an attachment, embed or sticker"**. The idea is that chains containing attachments mainly tend to flood the chat and are common, preventing said chains would be helpful.
_NOTE: I may break down this component into 2 later on. One variant focusing only on sticker(+emoji) chains and the other focusing on attachment chains._

## Possible upcoming components
There are more components that I plan to add. I will briefly explain them below.

### Total Attachment Limit
Another common form of misuse or spam is people who send a lot of attachments in general chats, way more than the average user. 
Therefore the idea is to set a per-user limit that resets after some time. The rule would be something like **"Users are allowed to send only X amount of attachments every Y time unit (minutes, days, TBC). Each user has their own counter"**. 
A simple baseline would be to go for daily limits, it's probably the most common and most straightforward time unit for this scenario. The more delicate part is about choosing the attachment limit, since a limit too low will affect too many users, many who are technically false positives, while a limit too high will not address the issue. Therefore, a bonus consideration to address this issue is to gather information to obtain an average of how many attachments are sent daily, by how many users. Though, this stat gathering would end up being a bot feature of its own.

### Consecutive Message Chain prevention
Another type of chain is when attachments are sent consecutively with no regular messages in between them. This works a bit differently from the chain reply automod though feels very similar in purpose. The rule would look like **"users are allowed to send only X consecutive messages of Y type."**. The type could be attachments or stickers, or even emotes. 

# What's planned next.
Since this is a checkpoint, I will cover other features that I plan to implement in the near or not so near future. There is no set order of what will come before, it's more like an unordered list of things that need to be done.
- Add the config option for setting and modifying the logging channel for the various components. Planned to be added to the existing modals.
- Add a nice embed display for the automod logs. Possibly add buttons, like one to unmute the person or something
- Implement the planned automod components listed above.
- Implement a sort of listener that watches a specific channel and gathers data for a defined period of time. The data to be gathered will include: user_id, gif counter, attachment counter, total media count. The data mentioned previously will be classified by day.
- Customizability for the automod actions (dm, timeout, etc.) to be fine-tuned by server admins for their server. Currently hard-coded.
- Alert/priority system. Upon receiving a message deletion event (or even the bot itself deleting a message), the bot should alert the automods watching that channel to reflect the deletion within the memory to avoid unwanted interactions. Priority system should be an internal ranking of priorirty for the automod components. This is to handle events where two components flag the same message, the system should pick the highest priority automod component and simply send an alert to the other automod components.
- Data logging (possibly among the last things implemented). Basically add a logging sub-system to make the flow of data throughout the system much more traceable so as to help with debugging. Though, it'd probably need to be disabled when in production, for ethical reasons.
- further improved architecture. Where things are more centralized, possibly a master config file, enhanced modularity (like, contorl on which components the bot allows usage of).
- Possible dashboard (not expected anytime soon LOL). Since modifying server settings from a website is often easier. 
- Migrating from JSON storage to database (sqlite). Though, this must be kept for after, since the JSON based storage is a lot more flexible when the structure of the data we store changes actively, so that's more of a final step before deployment into production.

