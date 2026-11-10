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
# Google Sheets 設定（在此處加入了新的 "spell" 分頁）
# -------------------------------------------------------------
SHEET_ID = "1FiReFPYNbgFhgLcNuZ43bxtrJ9R92vqKpuD6OQDwKjo"
SHEETS = {
    "Basic": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Basic",
    "Advanced": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Advanced",
    "Weapon": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Weapon",
    "Armor": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Armor",
    "spell": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=spell"
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
        if 'Item' not in df.columns and 'Spell' not in df.columns and 'D' not in df.columns:
            continue
            
        has_cn_item = 'Item_CN' in df.columns or 'Item CN' in df.columns
        if has_cn_item:
            matches = df[
                (df.get('Item', pd.Series()).astype(str).str.strip().str.lower() == target) |
                (df.get('Item_CN', pd.Series()).astype(str).str.strip().str.lower() == target) |
                (df.get('Item CN', pd.Series()).astype(str).str.strip().str.lower() == target)
            ]
        else:
            matches = df[df.get('Item', pd.Series()).astype(str).str.strip().str.lower() == target]
            
        if not matches.empty:
            row = matches.iloc[0]
            item_name = get_row_value(row, df.columns, ['Item', 'Spell', df.columns[3] if len(df.columns) > 3 else ''])
            cn_name = get_row_value(row, df.columns, ['Item_CN', 'Item CN', 'Chinese Item', df.columns[4] if len(df.columns) > 4 else ''])
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
                
            eff_str = get_row_value(row, df.columns, ['Effects', 'Effect', 'Description'])
            if eff_str:
                embed.add_field(name="Effects / Description (效果/說明)", value=eff_str, inline=False)
                
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

# --- 支援分頁按鈕的 View 類別 ---
class SkillPaginatorView(discord.ui.View):
    def __init__(self, chunks, title_name):
        super().__init__(timeout=180)
        self.chunks = chunks
        self.title_name = title_name
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.chunks) - 1

    def get_current_embed(self):
        desc = "\n".join(self.chunks[self.current_page])
        embed = discord.Embed(
            title=f"📜 Spell/Skill List: {self.title_name} (Page {self.current_page + 1}/{len(self.chunks)})",
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

# --- 核心查詢處理（同時支援工作技能與 Spell 頁面查詢） ---
def get_skill_paginator(query_name: str):
    converted_query = converter.convert(query_name)
    target = converted_query.strip().lower()
    raw_results = []
    try:
        for sheet_name, df in cached_dfs.items():
            # 針對 spell 分頁的特殊欄位對應（根據你的截圖結構調整）
            if sheet_name == 'spell':
                # 假設欄位順序或名稱：Col A=Class(CN), Col B=Class(EN), Col C=Spell(CN), Col D=Spell(EN), Col E=SkillTree, Col F=Desc(CN), Col G=Desc(EN) 等
                # 我們用通用字串比對找出符合該 Class (例如 mage / archmage / 法師 / 巫師) 的列
                match_rows = df[
                    df.astype(str).apply(lambda row: row.str.lower().str.contains(target).any(), axis=1)
                ]
                for _, row in match_rows.iterrows():
                    # 抓取欄位資料（安全檢查避免 Index Error）
                    cols = list(df.columns)
                    class_cn = str(row.iloc[0]) if len(cols) > 0 and pd.notna(row.iloc[0]) else ''
                    class_en = str(row.iloc[1]) if len(cols) > 1 and pd.notna(row.iloc[1]) else ''
                    spell_cn = str(row.iloc[2]) if len(cols) > 2 and pd.notna(row.iloc[2]) else ''
                    spell_en = str(row.iloc[3]) if len(cols) > 3 and pd.notna(row.iloc[3]) else ''
                    skill_tree = str(row.iloc[4]) if len(cols) > 4 and pd.notna(row.iloc[4]) else ''
                    desc_cn = str(row.iloc[5]) if len(cols) > 5 and pd.notna(row.iloc[5]) else ''
                    desc_en = str(row.iloc[6]) if len(cols) > 6 and pd.notna(row.iloc[6]) else ''

                    # 確認這列確實屬於使用者搜尋的 Class (英文或中文)
                    if target in class_en.lower() or target in class_cn.lower():
                        spell_display = f"{spell_en} ({spell_cn})" if spell_cn else spell_en
                        line_parts = [f"• **{spell_display}** [{class_en}/{class_cn}]"]
                        if skill_tree and skill_tree.lower() != 'nan':
                            line_parts.append(f"  └ Skill Tree (技能樹): `{skill_tree}`")
                        if desc_en and desc_en.lower() != 'nan':
                            line_parts.append(f"  └ Desc (英文): `{desc_en}`")
                        if desc_cn and desc_cn.lower() != 'nan':
                            line_parts.append(f"  └ 說明 (中文): {desc_cn}")

                        text_line = "\n".join(line_parts) + "\n"
                        raw_results.append({
                            'sort_key': spell_en,
                            'text': text_line
                        })
            else:
                # 處理原本的工作技能分頁 (Basic, Advanced, Weapon, Armor)
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
            # 如果是工作技能就用等級排序，如果是法術清單就用名稱排序
            if any('level' in r for r in raw_results):
                raw_results.sort(key=lambda x: x.get('level', 999))
            
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
                
            view = SkillPaginatorView(chunks, query_name)
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

# --- 2. 前綴指令：!skill (或可用來查詢類別如 !skill mage) ---
@bot.command(name="skill")
async def prefix_skill(ctx, *, skill_name: str = None):
    if not skill_name:
        await ctx.send("❓ Please provide a work skill or class name. Example: `!skill Mage`")
        return
    
    embed, view = get_skill_paginator(skill_name)
    if embed:
        await ctx.send(embed=embed, view=view)
    else:
        await ctx.send(f"❌ No items or spells found for **'{skill_name}'**.")

# --- 3. 斜線指令：/search ---
@bot.tree.command(name="search", description="Search for any item, skill, or recipe across all databases.")
@app_commands.describe(name="Type part of the item name")
@app_commands.autocomplete(name=item_autocomplete if 'item_autocomplete' in globals() else None)
async def search_command(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    embed = search_item_in_cache(name)
    if embed:
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(f"❌ Sorry, no item matching **'{name}'** was found.")

# --- 4. 斜線指令：/skill (同時支援 /skill mage, /skill archmage 或中文職業) ---
@bot.tree.command(name="skill", description="View a sorted list of all items or spells for a specific Work Skill or Class.")
@app_commands.describe(skill_name="Type or select the work skill or class (e.g., Mage, ArchMage, 法師)")
async def skill_command(interaction: discord.Interaction, skill_name: str):
    await interaction.response.defer()
    embed, view = get_skill_paginator(skill_name)
    if embed:
        await interaction.followup.send(embed=embed, view=view)
    else:
        await interaction.followup.send(f"❌ No items or spells found for **'{skill_name}'**.")

token = os.environ.get("DISCORD_TOKEN")
if not token:
    print("ERROR: DISCORD_TOKEN environment variable is missing!")
else:
    bot.run(token)
