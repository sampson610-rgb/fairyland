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
import opencc

# 初始化 OpenCC 簡轉繁轉換器
converter = opencc.OpenCC('s2t')

# --- 1. Render 專用：背景輕量網頁伺服器 ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")
    
    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# -------------------------------------------------------------
# Google Sheets 設定
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
        MY_GUILD = discord.Object(id=1561353756170395719)
        bot.tree.copy_global_to(guild=MY_GUILD)
        synced = await bot.tree.sync(guild=MY_GUILD)
        print(f"Successfully synced {len(synced)} command(s) to specific guild.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# --- 共用物品搜尋邏輯 ---
def search_item_in_cache(name: str):
    converted_name = converter.convert(name)
    target = converted_name.strip().lower()

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

            work_skill_cn = str(row['WorkSkill_CN']) if ('WorkSkill_CN' in df.columns and pd.notna(row.get('WorkSkill_CN'))) else ''
            work_skill_display = f"{work_skill_val} ({work_skill_cn})" if work_skill_cn and work_skill_cn.lower() != 'nan' else work_skill_val

            level_val = str(row['Level']) if 'Level' in df.columns and pd.notna(row.get('Level')) else 'N/A'
            
            embed = discord.Embed(title=title, color=discord.Color.blue())
            embed.add_field(name="Work Skill", value=work_skill_display, inline=True)
            embed.add_field(name="Required Level", value=level_val, inline=True)
            
            loc_str = str(row['Location']) if 'Location' in df.columns and pd.notna(row.get('Location')) else ''
            loc_cn_str = str(row['Location_CN']) if 'Location_CN' in df.columns and pd.notna(row.get('Location_CN')) else ''
            
            if loc_str and loc_str.lower() != 'nan':
                loc_display = f"{loc_str}\n{loc_cn_str}" if loc_cn_str and loc_cn_str.lower() != 'nan' else loc_str
                embed.add_field(name="Location", value=loc_display, inline=False)
                
            if 'Effects' in df.columns and pd.notna(row.get('Effects')):
                embed.add_field(name="Effects", value=str(row['Effects']), inline=False)
                
            if 'Ingredients' in df.columns and pd.notna(row.get('Ingredients')):
                ing_str = str(row['Ingredients'])
                ing_cn = str(row['Ingredients_CN']) if ('Ingredients_CN' in df.columns and pd.notna(row.get('Ingredients_CN'))) else ''
                ing_display = f"{ing_str} | {ing_cn}" if ing_cn and ing_cn.lower() != 'nan' else ing_str
                embed.add_field(name="Ingredients", value=ing_display, inline=False)
                
            if 'Exp' in df.columns and pd.notna(row.get('Exp')):
                embed.add_field(name="EXP", value=str(row['Exp']), inline=True)
                
            embed.set_footer(text="Source: Ahgang/知足常樂資料庫")
            return embed
    return None

# --- 物品自動完成 ---
async def item_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    choices = []
    converted_current = converter.convert(current)
    target = converted_current.strip().lower()
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

# --- 工作技能自動完成 ---
async def skill_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    skills = set()
    converted_current = converter.convert(current)
    target = converted_current.strip().lower()
    try:
        for sheet_name, df in cached_dfs.items():
            cols_to_check = [c for c in ['WorkSkill', 'Work Skill', 'WorkSkill_CN'] if c in df.columns]
            if not cols_to_check and len(df.columns) > 0:
                cols_to_check = [df.columns[0]]
                
            for col in cols_to_check:
                for val in df[col].dropna().astype(str):
                    if target in val.lower() and val.lower() not in ['item', 'workskill', 'work skill', 'workskill_cn']:
                        skills.add(val)
    except Exception as e:
        print(f"Skill autocomplete error: {e}")
    return [app_commands.Choice(name=s, value=s) for s in list(skills)[:25]]

# --- 核心技能清單建構函式（同時顯示中文材料 Ingredients_CN） ---
def build_skill_embed(skill_name: str):
    converted_skill_name = converter.convert(skill_name)
    target = converted_skill_name.strip().lower()
    raw_results = []
    try:
        for sheet_name, df in cached_dfs.items():
            has_ws_cn = 'WorkSkill_CN' in df.columns
            col_ws = None
            for col in ['WorkSkill', 'Work Skill']:
                if col in df.columns:
                    col_ws = col
                    break
            
            if not col_ws or 'Item' not in df.columns:
                continue

            if has_ws_cn:
                matches = df[
                    (df[col_ws].astype(str).str.strip().str.lower() == target) |
                    (df['WorkSkill_CN'].astype(str).str.strip().str.lower() == target)
                ]
            else:
                matches = df[df[col_ws].astype(str).str.strip().str.lower() == target]

            for _, row in matches.iterrows():
                item = str(row['Item'])
                cn_item = str(row['Item_CN']) if ('Item_CN' in df.columns and pd.notna(row.get('Item_CN'))) else ''
                
                if cn_item and cn_item.lower() != 'nan' and cn_item != item:
                    item_display = f"{item} ({cn_item})"
                else:
                    item_display = item

                lvl_raw = row.get('Level') if 'Level' in df.columns else '999'
                try:
                    lvl_num = int(float(lvl_raw))
                except:
                    lvl_num = 999 

                # 檢查 Effects 效果
                effects_val = str(row['Effects']) if ('Effects' in df.columns and pd.notna(row.get('Effects'))) else ''
                
                # 檢查 Ingredients 材料與中文材料 Ingredients_CN
                ing_val = str(row['Ingredients']) if ('Ingredients' in df.columns and pd.notna(row.get('Ingredients'))) else ''
                ing_cn_val = str(row['Ingredients_CN']) if ('Ingredients_CN' in df.columns and pd.notna(row.get('Ingredients_CN'))) else ''
                
                extra_info = []
                if effects_val and effects_val.lower() != 'nan':
                    extra_info.append(f"Effects: `{effects_val}`")
                
                if ing_val and ing_val.lower() != 'nan':
                    ing_display = f"{ing_val} ({ing_cn_val})" if ing_cn_val and ing_cn_val.lower() != 'nan' else ing_val
                    extra_info.append(f"Ing: `{ing_display}`")

                details_str = " | ".join(extra_info)
                if details_str:
                    text_line = f"• **Lvl {lvl_num}** : {item_display} | {details_str}"
                else:
                    text_line = f"• **Lvl {lvl_num}** : {item_display}"
                    
                raw_results.append({
                    'level': lvl_num,
                    'text': text_line
                })
                
        if raw_results:
            raw_results.sort(key=lambda x: x['level'])
            desc = "\n".join([r['text'] for r in raw_results])
            if len(desc) > 4000:
                desc = desc[:3996] + "..."
                
            embed = discord.Embed(title=f"🛠️ Work Skill List: {skill_name}", description=desc, color=discord.Color.gold())
            embed.set_footer(text="Source: Ahgang/知足常樂資料庫")
            return embed
    except Exception as e:
        print(f"Skill list builder error: {e}")
    return None

# --- 1. 前綴指令：!search ---
@bot.command(name="search")
async def prefix_search(ctx, *, name: str = None):
    if not name:
        await ctx.send("❓ Please provide an item name. Example: `!search apple`")
        return
    embed = search_item_in_cache(name)
    if embed:
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ Sorry, no item matching **'{name}'** was found.")

# --- 2. 前綴指令：!skill ---
@bot.command(name="skill")
async def prefix_skill(ctx, *, skill_name: str = None):
    if not skill_name:
        await ctx.send("❓ Please provide a work skill name. Example: `!skill Apothecary`")
        return
    
    embed = build_skill_embed(skill_name)
    if embed:
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ No items found for skill **'{skill_name}'**.")

# --- 3. 斜線指令：/search ---
@bot.tree.command(name="search", description="Search for any item, skill, or recipe across all databases.")
@app_commands.describe(name="Type part of the item name")
@app_commands.autocomplete(name=item_autocomplete)
async def search_command(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    embed = search_item_in_cache(name)
    if embed:
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(f"❌ Sorry, no item matching **'{name}'** was found.")

# --- 4. 斜線指令：/skill ---
@bot.tree.command(name="skill", description="View a sorted list of all items for a specific Work Skill.")
@app_commands.describe(skill_name="Type or select the work skill")
@app_commands.autocomplete(skill_name=skill_autocomplete)
async def skill_command(interaction: discord.Interaction, skill_name: str):
    await interaction.response.defer()
    embed = build_skill_embed(skill_name)
    if embed:
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(f"❌ No items found for skill **'{skill_name}'**.")

token = os.environ.get("DISCORD_TOKEN")
if not token:
    print("ERROR: DISCORD_TOKEN environment variable is missing!")
else:
    bot.run(token)
