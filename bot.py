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

# --- 輔助函式：安全取得欄位值 ---
def get_row_value(row, df_columns, possible_keys):
    for key in possible_keys:
        if key in df_columns and pd.notna(row.get(key)):
            val = str(row[key]).replace('\r', '').replace('\n', ' ').strip()
            if val and val.lower() != 'nan':
                return val
    return ''

# --- 共用物品搜尋邏輯（單一物品詳細資訊） ---
def search_item_in_cache(name: str):
    converted_name = converter.convert(name)
    target = converted_name.strip().lower()

    for sheet_name, df in cached_dfs.items():
        if 'Item' not in df.columns:
            continue
            
        has_cn_item = 'Item_CN' in df.columns or 'Item CN' in df.columns
        if has_cn_item:
            matches = df[
                (df['Item'].astype(str).str.strip().str.lower() == target) |
                (df.get('Item_CN', pd.Series()).astype(str).str.strip().str.lower() == target) |
                (df.get('Item CN', pd.Series()).astype(str).str.strip().str.lower() == target)
            ]
        else:
            matches = df[df['Item'].astype(str).str.strip().str.lower() == target]
            
        if not matches.empty:
            row = matches.iloc[0]
            item_name = str(row['Item'])
            cn_name = get_row_value(row, df.columns, ['Item_CN', 'Item CN', 'Chinese Item'])
            if not cn_name:
                cn_name = item_name
            title = f"📦 Item Info: {item_name} ({cn_name})" if cn_name != item_name else f"📦 Item Info: {item_name}"
            
            work_skill_val = get_row_value(row, df.columns, ['Work Skill', 'WorkSkill', df.columns[0]])
            work_skill_cn = get_row_value(row, df.columns, ['WorkSkill_CN', 'Work Skill CN', 'WorkSkill CN'])
            work_skill_display = f"{work_skill_val} ({work_skill_cn})" if work_skill_cn else work_skill_val

            level_val = get_row_value(row, df.columns, ['Level'])
            if not level_val:
                level_val = 'N/A'
            
            embed = discord.Embed(title=title, color=discord.Color.blue())
            
            embed.add_field(name="Work Skill (工作技能)", value=work_skill_display, inline=True)
            embed.add_field(name="Required Level (需求等級)", value=level_val, inline=True)
            
            loc_str = get_row_value(row, df.columns, ['Location'])
            loc_cn_str = get_row_value(row, df.columns, ['Location_CN', 'Location CN'])
            
            if loc_str:
                loc_display = f"`{loc_str}`\n{loc_cn_str}" if loc_cn_str else f"`{loc_str}`"
                embed.add_field(name="Location (地點)", value=loc_display, inline=False)
                
            eff_str = get_row_value(row, df.columns, ['Effects', 'Effect'])
            if eff_str:
                embed.add_field(name="Effects (效果)", value=eff_str, inline=False)
                
            ing_str = get_row_value(row, df.columns, ['Ingredients', 'Ingredient'])
            ing_cn = get_row_value(row, df.columns, ['Ingredients_CN', 'Ingredients CN', 'Ingredient_CN', 'Ingredient CN'])
            if ing_str:
                ing_display = f"`{ing_str}`\n{ing_cn}" if ing_cn else f"`{ing_str}`"
                embed.add_field(name="Ingredients (原料)", value=ing_display, inline=False)
                
            exp_str = get_row_value(row, df.columns, ['Exp', 'EXP'])
            if exp_str:
                embed.add_field(name="EXP (經驗)", value=exp_str, inline=True)
                
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
            for cn_col in ['Item_CN', 'Item CN']:
                if cn_col in df.columns:
                    for item_cn in df[cn_col].dropna().astype(str):
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
            cols_to_check = [c for c in ['WorkSkill', 'Work Skill', 'WorkSkill_CN', 'Work Skill CN'] if c in df.columns]
            if not cols_to_check and len(df.columns) > 0:
                cols_to_check = [df.columns[0]]
                
            for col in cols_to_check:
                for val in df[col].dropna().astype(str):
                    if target in val.lower() and val.lower() not in ['item', 'workskill', 'work skill', 'workskill_cn', 'work skill cn']:
                        skills.add(val)
    except Exception as e:
        print(f"Skill autocomplete error: {e}")
    return [app_commands.Choice(name=s, value=s) for s in list(skills)[:25]]

# --- 支援分頁按鈕的 View 類別 ---
class SkillPaginatorView(discord.ui.View):
    def __init__(self, chunks, skill_name):
        super().__init__(timeout=180)
        self.chunks = chunks
        self.skill_name = skill_name
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.chunks) - 1

    def get_current_embed(self):
        desc = "\n".join(self.chunks[self.current_page])
        embed = discord.Embed(
            title=f"🛠️ Work Skill List: {self.skill_name} (Page {self.current_page + 1}/{len(self.chunks)})",
            description=desc,
            color=discord.Color.gold()
        )
        embed.set_footer(text="Source: Ahgang/知足常樂資料庫")
        return embed

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.chunks) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

# --- 核心技能清單建構函式（支援 Location 與 Ingredients 顯示） ---
def get_skill_paginator(skill_name: str):
    converted_skill_name = converter.convert(skill_name)
    target = converted_skill_name.strip().lower()
    raw_results = []
    try:
        for sheet_name, df in cached_dfs.items():
            col_ws = None
            for col in ['WorkSkill', 'Work Skill', 'WorkSkill_CN', 'Work Skill CN']:
                if col in df.columns:
                    col_ws = col
                    break
            if not col_ws and len(df.columns) > 0:
                col_ws = df.columns[0]
            
            if not col_ws or 'Item' not in df.columns:
                continue

            matches = df[
                (df[col_ws].astype(str).str.strip().str.lower() == target) |
                (df.get('WorkSkill_CN', pd.Series()).astype(str).str.strip().str.lower() == target) |
                (df.get('Work Skill CN', pd.Series()).astype(str).str.strip().str.lower() == target)
            ]

            for _, row in matches.iterrows():
                item = str(row['Item'])
                cn_item = get_row_value(row, df.columns, ['Item_CN', 'Item CN'])
                
                if cn_item and cn_item != item:
                    item_display = f"{item} ({cn_item})"
                else:
                    item_display = item

                lvl_raw = get_row_value(row, df.columns, ['Level'])
                try:
                    lvl_num = int(float(lvl_raw))
                except:
                    lvl_num = 999 

                loc_str = get_row_value(row, df.columns, ['Location'])
                loc_cn_str = get_row_value(row, df.columns, ['Location_CN', 'Location CN'])
                effects_val = get_row_value(row, df.columns, ['Effects', 'Effect'])
                ing_val = get_row_value(row, df.columns, ['Ingredients', 'Ingredient'])
                ing_cn_val = get_row_value(row, df.columns, ['Ingredients_CN', 'Ingredients CN', 'Ingredient_CN', 'Ingredient CN'])
                
                line_parts = [f"• **Lvl {lvl_num}** : {item_display}"]
                
                if loc_str:
                    if loc_cn_str:
                        line_parts.append(f"  └ Location (地點):\n    `{loc_str}`\n    {loc_cn_str}")
                    else:
                        line_parts.append(f"  └ Location (地點):\n    `{loc_str}`")

                if effects_val:
                    line_parts.append(f"  └ Effects (效果): `{effects_val}`")
                
                if ing_val:
                    if ing_cn_val:
                        line_parts.append(f"  └ Ingredients (原料):\n    `{ing_val}`\n    {ing_cn_val}")
                    else:
                        line_parts.append(f"  └ Ingredients (原料):\n    `{ing_val}`")

                text_line = "\n".join(line_parts) + "\n"
                    
                raw_results.append({
                    'level': lvl_num,
                    'text': text_line
                })
                
        if raw_results:
            raw_results.sort(key=lambda x: x['level'])
            
            chunks = []
            current_chunk = []
            current_length = 0
            
            for r in raw_results:
                line_len = len(r['text']) + 1
                if current_length + line_len > 3500:
                    chunks.append(current_chunk)
                    current_chunk = [r['text']]
                    current_length = line_len
                else:
                    current_chunk.append(r['text'])
                    current_length += line_len
            if current_chunk:
                chunks.append(current_chunk)
                
            view = SkillPaginatorView(chunks, skill_name)
            return view.get_current_embed(), view
    except Exception as e:
        print(f"Skill list builder error: {e}")
    return None, None

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
    
    embed, view = get_skill_paginator(skill_name)
    if embed:
        await ctx.send(embed=embed, view=view)
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
    embed, view = get_skill_paginator(skill_name)
    if embed:
        await interaction.followup.send(embed=embed, view=view)
    else:
        await interaction.followup.send(f"❌ No items found for skill **'{skill_name}'**.")

token = os.environ.get("DISCORD_TOKEN")
if not token:
    print("ERROR: DISCORD_TOKEN environment variable is missing!")
else:
    bot.run(token)
