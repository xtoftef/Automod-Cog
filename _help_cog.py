"""Optional help cog for testing. 
Real systems can ommit this cog completely if they already have an implementation of it among their cogs. Or copy and reuse this code if they find it useful.

"""

import discord
from discord import app_commands
from discord.ext import commands

class HelpDropdown(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        options = []
        
        # 1. Dynamically build options from loaded cogs
        for cog_name, cog in bot.cogs.items():
            # Skip internal or hidden cogs
            if cog_name.lower() in ("helpcog", "owner"):
                continue
            
            description = cog.description or "No description provided."
            options.append(
                discord.SelectOption(
                    label=cog_name,
                    description=description[:100], # Max description length for SelectOption
                    value=cog_name
                )
            )

        super().__init__(
            placeholder="Select a category to view commands...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        cog_name = self.values[0]
        cog = self.bot.get_cog(cog_name)
        
        if not cog:
            await interaction.response.send_message("Category not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📖 {cog_name} Commands",
            description=cog.description or "No category description.",
            color=discord.Color.blue()
        )

        # 2. Add commands belonging to the selected Cog
        # Works for both app_commands (slash) and traditional commands
        for cmd in cog.get_app_commands():
            embed.add_field(
                name=f"/{cmd.name}",
                value=cmd.description or "No description.",
                inline=False
            )

        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180)
        self.add_item(HelpDropdown(bot))


class HelpCog(commands.Cog):
    """Cog for managing the /help interface."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Shows available commands by category.")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Bot Help Menu",
            description="Select a category from the dropdown menu below to see available commands.",
            color=discord.Color.blurple()
        )
        view = HelpView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))