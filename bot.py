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
SHEET_NAME = "Sheet1"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def fetch_item_data(query_name: str):
    try:
        df = pd.read_csv(CSV_URL)
        df.columns = df.columns.str.strip()
        target = query_name.strip().lower()

        has_cn_col = 'Item_CN' in df.columns
        if has_cn_col:
            matches = df[
                (df['Item'].astype(str).str.strip().str.lower() == target) |
                (df['Item_CN'].astype(str).str.strip().str.lower() == target)
            ]
        else:
            matches = df[df['Item'].astype(str).str.strip().str.lower() == target]

        if not matches.empty:
            row = matches.iloc[0]
            english_name = str(row['Item'])
            cn_name = str(row['Item_CN']) if (has_cn_col and pd.notna(row['Item_CN'])) else english_name

            return {
                "found": True,
                "work_skill": str(row.get('WorkSkill', 'N/A')),
                "item": english_name,
                "item_cn": cn_name,
                "level": str(row.get('Level', 'N/A')),
                "exp": str(row.get('Exp', 'N/A')),
                "location": str(row.get('Location', 'N/A'))
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
@app_commands.describe(name="The name of the item to search (e.g. Apple or 蘋果)")
async def item_command(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    data = fetch_item_data(name)

    if data["found"]:
        title_text = f"🍏 Item Info: {data['item']} ({data['item_cn']})" if data['item_cn'] != data['item'] else f"🍏 Item Info: {data['item']}"
        embed = discord.Embed(title=title_text, color=discord.Color.green())
        embed.add_field(name="Work Skill", value=data["work_skill"], inline=True)
        embed.add_field(name="Required Level", value=data["level"], inline=True)
        embed.add_field(name="EXP", value=data["exp"], inline=True)
        embed.add_field(name="Location", value=data["location"], inline=False)
        embed.set_footer(text="Fairyland Online Item Database")
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(f"❌ Sorry, item **'{name}'** was not found in the database.")

token = os.environ.get("DISCORD_TOKEN")
if not token:
    print("ERROR: DISCORD_TOKEN environment variable is missing!")
else:
    bot.run(token)
