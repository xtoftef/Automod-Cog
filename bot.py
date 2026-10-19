"""This is the main entry point you can use to test the bot. Don't forget to create a .env file and add your bot token there"""

import os
import asyncio
import discord
from discord.ext import commands
import logging
import logging.handlers

from automod_cog import AutomodCog

TEST = True

# Configuration
if TEST:
    DISCORD_TOKEN = os.getenv("TEST_BOT_TOKEN", None)
else:
    DISCORD_TOKEN = os.getenv("PRODUCTION_BOT_TOKEN", None)


if not DISCORD_TOKEN:
    raise Exception("Bot token missing. Please add it to your .env file")



logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
logging.getLogger('discord.http').setLevel(logging.INFO)
# You might find the logger useful in case some of your functions raise errors but don't stop the bot
handler = logging.handlers.RotatingFileHandler(
    filename='discord.log',
    encoding='utf-8',
    maxBytes=32 * 1024 * 1024,  # 32 MiB
    #backupCount=5,  # Rotate through 5 files
)
dt_fmt = '%Y-%m-%d %H:%M:%S'
formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
handler.setFormatter(formatter)
logger.addHandler(handler)






async def main():
    if not DISCORD_TOKEN:
        raise Exception("Bot token missing. Please add it to your .env file")

    # 1. Setup Discord Bot
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.guilds = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        if not bot.user:
            raise Exception("Bot is not logged in")
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")
        print(bot.guilds)

        # Necessary to get all the guild data. Otherwise it initializes the automods when the bot didn't receive the guild data yet.
        automod_cog.automod_engine.guilds = list(bot.guilds)
        automod_cog.automod_engine.init_all_guilds_automod()


        # Sync slash commands
        await bot.tree.sync()
        print("Slash commands synced successfully.")

    # 2. Add Cogs & Adapters
    automod_cog = AutomodCog(bot)
    await bot.add_cog(automod_cog)

    # 3. Run Bot
    await bot.start(DISCORD_TOKEN)
    
    

if __name__ == "__main__":
    asyncio.run(main())