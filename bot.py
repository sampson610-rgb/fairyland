import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from discord import app_commands
import pandas as pd
import requests
import io

# Keep-alive web server for Render Free Web Service
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

# -------------------------------------------------------------
SHEET_ID = "1FiReFPYNbgFhgLcNuZ43bxtrJ9R92vqKpuD6OQDwKjo"
SHEETS = {
    "Basic": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Basic",
    "Advanced": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Advanced",
    "Weapon": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Weapon",
    "Armor": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Armor"
}
# -------------------------------------------------------------

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

# --- Helper function for recipe/equipment formatting ---
def format_recipe_embed(row, df, title_prefix, color):
    embed = discord.Embed(title=f"{title_prefix}: {row['Item']}", color=color)
    
    if len(df.columns) > 0 and df.columns[0] != 'Item':
        cat_col = df.columns[0]
        embed.add_field(name="Category", value=str(row.get(cat_col, 'N/A')), inline=True)
        
    embed.add_field(name="Required Level", value=str(row.get('Level', 'N/A')), inline=True)
    
    if 'Weight' in df.columns and pd.notna(row.get('Weight')):
        embed.add_field(name="Weight", value=str(row.get('Weight')), inline=True)
    if 'Exp' in df.columns and pd.notna(row.get('Exp')):
        embed.add_field(name="Exp", value=str(row.get('Exp')), inline=True)
    if 'Effects' in df.columns and pd.notna(row.get('Effects')):
        embed.add_field(name="Effects", value=str(row.get('Effects')), inline=False)
        
    embed.add_field(name="Ingredients", value=str(row.get('Ingredients', 'N/A')), inline=False)
    embed.set_footer(text="Fairyland Online Database")
    return embed

# --- Universal /search Command (Scans all 4 tabs) ---
@bot.tree.command(name="search", description="Search for any item or recipe across all databases (Basic, Advanced, Weapon, Armor).")
@app_commands.describe(name="The name of the item to search")
async def search_command(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    target = name.strip().lower()
    
    try:
        # 1. Check Basic Sheet
        resp = requests.get(SHEETS["Basic"])
        resp.encoding = 'utf-8'
        df_basic = pd.read_csv(io.StringIO(resp.text))
        df_basic.columns = df_basic.columns.str.strip()
        
        has_cn_item = 'Item_CN' in df_basic.columns
        has_cn_loc = 'Location_CN' in df_basic.columns

        if has_cn_item:
            matches = df_basic[
                (df_basic['Item'].astype(str).str.strip().str.lower() == target) |
                (df_basic['Item_CN'].astype(str).str.strip().str.lower() == target)
            ]
        else:
            matches = df_basic[df_basic['Item'].astype(str).str.strip().str.lower() == target]

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
            return

        # 2. Check Advanced, Weapon, Armor Sheets
        sheet_configs = [
            ("Advanced", "⚔️ Crafting Info", discord.Color.blue()),
            ("Weapon", "🗡️ Weapon Info", discord.Color.orange()),
            ("Armor", "🛡️ Armor Info", discord.Color.purple())
        ]

        for sheet_name, title_prefix, color in sheet_configs:
            resp = requests.get(SHEETS[sheet_name])
            resp.encoding = 'utf-8'
            df = pd.read_csv(io.StringIO(resp.text))
            df.columns = df.columns.str.strip()

            if 'Item' in df.columns:
                matches = df[df['Item'].astype(str).str.strip().str.lower() == target]
                if not matches.empty:
                    embed = format_recipe_embed(matches.iloc[0], df, title_prefix, color)
                    await interaction.followup.send(embed=embed)
                    return

        # If not found anywhere
        await interaction.followup.send(f"❌ Sorry, **'{name}'** was not found in any database.")
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error searching database: {e}")

token = os.environ.get("DISCORD_TOKEN")
if not token:
    print("ERROR: DISCORD_TOKEN environment variable is missing!")
else:
    bot.run(token)
