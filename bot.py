import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from discord import app_commands
import pandas as pd
import requests
import io
import time

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

cached_dfs = {}

def load_sheets_to_cache():
    global cached_dfs
    while True:
        try:
            new_dfs = {}
            for sheet_name, url in SHEETS.items():
                resp = requests.get(url)
                resp.encoding = 'utf-8'
                df = pd.read_csv(io.StringIO(resp.text))
                df.columns = df.columns.str.strip()
                new_dfs[sheet_name] = df
            cached_dfs = new_dfs
            print("Successfully cached Google Sheets data.")
        except Exception as e:
            print(f"Error caching sheets: {e}")
        time.sleep(600)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    threading.Thread(target=load_sheets_to_cache, daemon=True).start()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# --- Fast Autocomplete for Items ---
async def item_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    choices = []
    target = current.strip().lower()
    try:
        for sheet_name, df in cached_dfs.items():
            if 'Item' in df.columns:
                for item in df['Item'].dropna().astype(str):
                    if target in item.lower():
                        if item not in [c.name for c in choices]:
                            choices.append(app_commands.Choice(name=item, value=item))
            if 'Item_CN' in df.columns:
                for item_cn in df['Item_CN'].dropna().astype(str):
                    if target in item_cn.lower():
                        if item_cn not in [c.name for c in choices]:
                            choices.append(app_commands.Choice(name=item_cn, value=item_cn))
    except Exception as e:
        print(f"Autocomplete error: {e}")
    return choices[:25]

# --- Fast Autocomplete for Work Skills ---
async def skill_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    skills = set()
    target = current.strip().lower()
    try:
        for sheet_name, df in cached_dfs.items():
            col_to_check = None
            for col in ['WorkSkill', 'Work Skill']:
                if col in df.columns:
                    col_to_check = col
                    break
            if not col_to_check and len(df.columns) > 0:
                col_to_check = df.columns[0]
                
            if col_to_check:
                for val in df[col_to_check].dropna().astype(str):
                    if target in val.lower() and val.lower() not in ['item', 'workskill', 'work skill']:
                        skills.add(val)
    except Exception as e:
        print(f"Skill autocomplete error: {e}")
    return [app_commands.Choice(name=s, value=s) for s in list(skills)[:25]]

# --- Universal /search Command ---
@bot.tree.command(name="search", description="Search for any item or recipe")
@app_commands.describe(name="Type item name")
@app_commands.autocomplete(name=item_autocomplete)
async def search_command(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    target = name.strip().lower()
    
    try:
        found = False
        for sheet_name, df in cached_dfs.items():
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
                found = True
                
                item_name = str(row['Item'])
                cn_name = str(row['Item_CN']) if (has_cn_item and pd.notna(row.get('Item_CN'))) else item_name
                title = f"📦 Item Info: {item_name} ({cn_name})" if cn_name != item_name else f"📦 Item Info: {item_name}"
                
                work_skill_val = 'N/A'
                for col in ['Work Skill', 'WorkSkill']:
                    if col in df.columns and pd.notna(row.get(col)):
                        work_skill_val = str(row[col])
                        break
                if work_skill_val == 'N/A' and len(df.columns) > 0:
                    work_skill_val = str(row.iloc[0])

                level_val = str(row['Level']) if 'Level' in df.columns and pd.notna(row.get('Level')) else 'N/A'
                
                embed = discord.Embed(title=title, color=discord.Color.blue())
                
                embed.add_field(name="Work Skill (技能)", value=work_skill_val, inline=True)
                embed.add_field(name="Required Level (等级)", value=level_val, inline=True)
                
                if 'Location' in df.columns and pd.notna(row.get('Location')):
                    loc = str(row['Location'])
                    loc_cn = str(row['Location_CN']) if ('Location_CN' in df.columns and pd.notna(row.get('Location_CN'))) else loc
                    loc_display = f"{loc}\n{loc_cn}" if loc_cn != loc else loc
                    embed.add_field(name="Location (地点)", value=loc_display, inline=False)
                    
                if 'Effects' in df.columns and pd.notna(row.get('Effects')):
                    embed.add_field(name="Effects", value=str(row['Effects']), inline=False)
                    
                if 'Ingredients' in df.columns and pd.notna(row.get('Ingredients')):
                    embed.add_field(name="Ingredients", value=str(row['Ingredients']), inline=False)
                    
                if 'Exp' in df.columns and pd.notna(row.get('Exp')):
                    embed.add_field(name="EXP", value=str(row['Exp']), inline=True)
                    
                db_display = f"{sheet_name}基础技能" if sheet_name == "Basic" else sheet_name
                embed.set_footer(text=f"Database : {db_display} | Source ： Ahgang/知足常乐资料库")
                
                await interaction.followup.send(embed=embed)
                break
                
        if not found:
            await interaction.followup.send(f"❌ Sorry, **'{name}'** was not found in any database.")
        
    except Exception as e:
        print(f"Search error: {e}")
        await interaction.followup.send(f"❌ An error occurred while searching the database.")

# --- /skill Command ---
@bot.tree.command(name="skill", description="View sorted list of items for a work skill")
@app_commands.describe(skill_name="Type work skill")
@app_commands.autocomplete(skill_name=skill_autocomplete)
async def skill_command(interaction: discord.Interaction, skill_name: str):
    await interaction.response.defer()
    target = skill_name.strip().lower()
    raw_results = []
    
    try:
        for sheet_name, df in cached_dfs.items():
            col_to_check = None
            for col in ['WorkSkill', 'Work Skill']:
                if col in df.columns:
                    col_to_check = col
                    break
            if not col_to_check and len(df.columns) > 0:
                col_to_check = df.columns[0]
                
            if not col_to_check or 'Item' not in df.columns:
                continue
                
            matches = df[df[col_to_check].astype(str).str.strip().str.lower() == target]
            for _, row in matches.iterrows():
                item = str(row['Item'])
                
                lvl_raw = row.get('Level') if 'Level' in df.columns else '999'
                try:
                    lvl_num = int(float(lvl_raw))
                except:
                    lvl_num = 999 
                    
                raw_results.append({
                    'level': lvl_num,
                    'text': f"• **Lvl {lvl_num}** : {item} `[{sheet_name}]`"
                })
                
        if raw_results:
            raw_results.sort(key=lambda x: x['level'])
            
            desc = "\n".join([r['text'] for r in raw_results])
            if len(desc) > 4000:
                desc = desc[:3996] + "..."
                
            embed = discord.Embed(title=f"🛠️ Work Skill List: {skill_name}", description=desc, color=discord.Color.gold())
            embed.set_footer(text="Source ： Ahgang/知足常乐资料库")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ No items found for skill **'{skill_name}'**.")
            
    except Exception as e:
        print(f"Skill list error: {e}")
        await interaction.followup.send(f"❌ An error occurred while fetching the skill list.")

token = os.environ.get("DISCORD_TOKEN")
if not token:
    print("ERROR: DISCORD_TOKEN environment variable is missing!")
else:
    bot.run(token)
