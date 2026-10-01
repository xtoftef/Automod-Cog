import discord
from discord.app_commands.commands import commands

class AutomodCog(commands.Cog):
    "you can implement the commands and logic here, it also still supports the on_message function."

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        #self.memory = memory # you'll want to uncomment this if you plan on adding persistent memory
        # you may modify the constructor if you see it needed
        ...

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        ...
        # TODO: I guess this is where you'll add the filtering logic per channel and all that stuff. Try to wrap them under functions
        # The listener will just trigger this anytime the bot receives a message from a server it is listening to.