import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from discord import app_commands
import pandas as pd

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

SHEET_ID = "1FiReFPYNbgFhgLcNuZ43bxtrJ9R92vqKpuD6OQDwKjo"

# URLs for both Sheet tabs
BASIC_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Sheet1"
ADVANCE_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Advance"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# --- Existing /item Command ---
@bot.tree.command(name="item", description="Look up basic item skills, levels, and location.")
@app_commands.describe(name="The name of the item to search (e.g. Apple or 蘋果)")
async def item_command(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    try:
        df = pd.read_csv(BASIC_CSV_URL)
        df.columns = df.columns.str.strip()
        target = name.strip().lower()

        has_cn_item = 'Item_CN' in df.columns
        has_cn_loc = 'Location_CN' in df.columns

        if has_cn_item:
            matches = df[
                (df['Item'].astype(str).str.strip().str.lower() == target) |
                (df['Item_CN'].astype(str).str.strip().str.lower() == target)
            ]
        else:
            matches = df[df['Item'].astype(str).str.strip().str.lower() == target]

        if not matches.empty:
            row = matches.iloc[0]
            english_name = str(row['Item'])
            cn_name = str(row['Item_CN']) if (has_cn_item and pd.notna(row['Item_CN'])) else english_name
            
            english_loc = str(row.get('Location', 'N/A'))
            cn_loc = str(row['Location_CN']) if (has_cn_loc and pd.notna(row['Location_CN'])) else english_loc

            title_text = f"🍏 Item Info: {english_name} ({cn_name})" if cn_name != english_name else f"🍏 Item Info: {english_name}"
            loc_display = f"{english_loc}\n{cn_loc}" if cn_loc != english_loc else english_loc

            embed = discord.Embed(title=title_text, color=discord.Color.green())
            embed.add_field(name="Work Skill", value=str(row.get('WorkSkill', 'N/A')), inline=True)
            embed.add_field(name="Required Level", value=str(row.get('Level', 'N/A')), inline=True)
            embed.add_field(name="EXP", value=str(row.get('Exp', 'N/A')), inline=True)
            embed.add_field(name="Location", value=loc_display, inline=False)
            embed.set_footer(text="Fairyland Online Item Database")
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ Sorry, item **'{name}'** was not found in the basic database.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error fetching basic data: {e}")

# --- New /craft Command for Advanced Skills ---
@bot.tree.command(name="craft", description="Look up advanced crafting ingredients and details.")
@app_commands.describe(name="The name of the crafted item")
async def craft_command(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    try:
        df = pd.read_csv(ADVANCE_CSV_URL)
        df.columns = df.columns.str.strip()
        target = name.strip().lower()

        # Assuming columns in 'Advance' tab: CraftSkill, Item, Ingredients, Level, etc.
        matches = df[df['Item'].astype(str).str.strip().str.lower() == target]

        if not matches.empty:
            row = matches.iloc[0]
            embed = discord.Embed(title=f"⚔️ Crafting Info: {row['Item']}", color=discord.Color.blue())
            embed.add_field(name="Craft Skill", value=str(row.get('CraftSkill', 'N/A')), inline=True)
            embed.add_field(name="Required Level", value=str(row.get('Level', 'N/A')), inline=True)
            embed.add_field(name="Ingredients", value=str(row.get('Ingredients', 'N/A')), inline=False)
            embed.set_footer(text="Fairyland Online Crafting Database")
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ Sorry, recipe for **'{name}'** was not found in the advanced database.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error fetching crafting data: {e}")

token = os.environ.get("DISCORD_TOKEN")
if token:
    bot.run(token)
