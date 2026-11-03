import os
import discord
from discord.ext import commands
from discord import app_commands
import pandas as pd

# -------------------------------------------------------------
# Replace with your actual Google Sheet ID and Sheet tab name!
SHEET_ID = "YOUR_SPREADSHEET_ID_HERE"
SHEET_NAME = "Sheet1"  # Or "Form_Responses", "Basic Skills", etc.
# -------------------------------------------------------------

# Direct CSV export URL for Google Sheets
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def fetch_item_data(item_name: str):
    """Fetch and search item data directly from the Google Sheet."""
    try:
        df = pd.read_csv(CSV_URL)
        df.columns = df.columns.str.strip()
        
        # Column mapping based on your sheet layout:
        # Column A (index 0): Work Skill
        # Column B (index 1): Item Name
        # Column C (index 2): Required Level
        # Column D (index 3): EXP
        # Column E (index 4): Location
        item_col = df.columns[1] 
        
        matches = df[df[item_col].astype(str).str.strip().str.lower() == item_name.strip().lower()]
        
        if not matches.empty:
            row = matches.iloc[0]
            return {
                "found": True,
                "work_skill": str(row.iloc[0]),
                "item": str(row.iloc[1]),
                "level": str(row.iloc[2]),
                "exp": str(row.iloc[3]),
                "location": str(row.iloc[4])
            }
    except Exception as e:
        print(f"Error fetching sheet data: {e}")
    
    return {"found": False}

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="item", description="Look up item skills, levels, and location.")
@app_commands.describe(name="The name of the item to search (e.g. Apple)")
async def item_command(interaction: discord.Interaction, name: str):
    await interaction.response.defer() # Gives the bot time to fetch live data
    
    data = fetch_item_data(name)
    
    if data["found"]:
        embed = discord.Embed(
            title=f"🍏 Item Info: {data['item']}",
            color=discord.Color.green()
        )
        embed.add_field(name="Work Skill", value=data["work_skill"], inline=True)
        embed.add_field(name="Required Level", value=data["level"], inline=True)
        embed.add_field(name="EXP", value=data["exp"], inline=True)
        embed.add_field(name="Location", value=data["location"], inline=False)
        embed.set_footer(text="Fairyland Online Item Database")
        
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(f"❌ Sorry, item **'{name}'** was not found in the database.")

# Start bot using environment variable
bot.run(os.environ.get("DISCORD_TOKEN"))
