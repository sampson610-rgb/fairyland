import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from discord import app_commands
import pandas as pd
import requests
import io

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

@bot.tree.command(name="search", description="Search for any item, skill, or recipe across all databases.")
@app_commands.describe(name="The name of the item to search (e.g. Apple or Ginger Tea)")
async def search_command(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    target = name.strip().lower()
    
    sheets_to_check = ["Basic", "Advanced", "Weapon", "Armor"]
    
    try:
        for sheet_name in sheets_to_check:
            url = SHEETS[sheet_name]
            resp = requests.get(url)
            resp.encoding = 'utf-8'
            df = pd.read_csv(io.StringIO(resp.text))
            df.columns = df.columns.str.strip()
            
            if 'Item' not in df.columns:
                continue
                
            has_cn_item = 'Item_CN' in df.columns
            if has_cn_item:
                matches = df[
                    (df['Item'].astype(str).str.strip().str.lower() == target) |
                    (df['Item_CN'].astype(str).str.strip().str.lower() == target)
                ]
            else:
                matches = df[df['Item'].astype(str).str.strip().str.lower() == target]
                
            if not matches.empty:
                row = matches.iloc[0]
                
                item_name = str(row['Item'])
                cn_name = str(row['Item_CN']) if (has_cn_item and pd.notna(row.get('Item_CN'))) else item_name
                title = f"📦 Item Info: {item_name} ({cn_name})" if cn_name != item_name else f"📦 Item Info: {item_name}"
                
                # Grab Work Skill (supports both 'Work Skill' and 'WorkSkill' headers, or falls back to column A)
                work_skill_val = 'N/A'
                for col in ['Work Skill', 'WorkSkill']:
                    if col in df.columns and pd.notna(row.get(col)):
                        work_skill_val = str(row[col])
                        break
                if work_skill_val == 'N/A' and len(df.columns) > 0:
                    work_skill_val = str(row.iloc[0])

                level_val = str(row['Level']) if 'Level' in df.columns and pd.notna(row.get('Level')) else 'N/A'
                
                embed = discord.Embed(title=title, color=discord.Color.blue())
                embed.add_field(name="Work Skill", value=work_skill_val, inline=True)
                embed.add_field(name="Required Level", value=level_val, inline=True)
                
                # Location (if available in Basic tab)
                if 'Location' in df.columns and pd.notna(row.get('Location')):
                    loc = str(row['Location'])
                    loc_cn = str(row['Location_CN']) if ('Location_CN' in df.columns and pd.notna(row.get('Location_CN'))) else loc
                    loc_display = f"{loc}\n{loc_cn}" if loc_cn != loc else loc
                    embed.add_field(name="Location", value=loc_display, inline=False)
                    
                # Effects (if available)
                if 'Effects' in df.columns and pd.notna(row.get('Effects')):
                    embed.add_field(name="Effects", value=str(row['Effects']), inline=False)
                    
                # Ingredients (if available in Advanced/Weapon/Armor)
                if 'Ingredients' in df.columns and pd.notna(row.get('Ingredients')):
                    embed.add_field(name="Ingredients", value=str(row['Ingredients']), inline=False)
                    
                # EXP (if available)
                if 'Exp' in df.columns and pd.notna(row.get('Exp')):
                    embed.add_field(name="EXP", value=str(row['Exp']), inline=True)
                    
                embed.set_footer(text=f"Database: {sheet_name} | Fairyland Online")
                await interaction.followup.send(embed=embed)
                return
                
        await interaction.followup.send(f"❌ Sorry, **'{name}'** was not found in any database.")
        
    except Exception as e:
        print(f"Search error: {e}")
        await interaction.followup.send(f"❌ An error occurred while searching the database.")

token = os.environ.get("DISCORD_TOKEN")
if not token:
    print("ERROR: DISCORD_TOKEN environment variable is missing!")
else:
    bot.run(token)
