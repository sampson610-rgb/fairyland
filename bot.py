# --- Prefix Command: !search ---
@bot.command(name="search")
async def prefix_search(ctx, *, name: str = None):
    if not name:
        await ctx.send("❓ Please provide an item name. Example: `!search Wooden Rod`")
        return

    target = name.strip().lower()
    found = False

    try:
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
                title = f"📦 物品資訊: {item_name} ({cn_name})" if cn_name != item_name else f"📦 物品資訊: {item_name}"

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
                embed.add_field(name="Work Skill (技能)", value=work_skill_display, inline=True)
                embed.add_field(name="Required Level (等級)", value=level_val, inline=True)

                loc_str = str(row['Location']) if 'Location' in df.columns and pd.notna(row.get('Location')) else ''
                loc_cn_str = str(row['Location_CN']) if 'Location_CN' in df.columns and pd.notna(row.get('Location_CN')) else ''

                if loc_str and loc_str.lower() != 'nan':
                    loc_display = f"{loc_str}\n{loc_cn_str}" if loc_cn_str and loc_cn_str.lower() != 'nan' else loc_str
                    embed.add_field(name="Location (地點)", value=loc_display, inline=False)

                if 'Effects' in df.columns and pd.notna(row.get('Effects')):
                    embed.add_field(name="Effects (效果)", value=str(row['Effects']), inline=False)

                if 'Ingredients' in df.columns and pd.notna(row.get('Ingredients')):
                    embed.add_field(name="Ingredients (材料)", value=str(row['Ingredients']), inline=False)

                if 'Exp' in df.columns and pd.notna(row.get('Exp')):
                    embed.add_field(name="EXP (經驗)", value=str(row['Exp']), inline=True)

                db_display = f"{sheet_name}基礎技能" if sheet_name == "Basic" else sheet_name
                embed.set_footer(text=f"Database : {db_display} | Source ： Ahgang/知足常樂資料庫")

                await ctx.send(embed=embed)
                break

        if not found:
            await ctx.send(f"❌ 抱歉，在任何資料庫中都找不到 **'{name}'**。")

    except Exception as e:
        print(f"Prefix search error: {e}")
        await ctx.send("❌ 搜尋資料庫時發生錯誤。")


# --- Prefix Command: !skill ---
@bot.command(name="skill")
async def prefix_skill(ctx, *, skill_name: str = None):
    if not skill_name:
        await ctx.send("❓ Please provide a skill name. Example: `!skill Woodcutting`")
        return

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

            embed = discord.Embed(title=f"🛠️ 工作技能清單: {skill_name}", description=desc, color=discord.Color.gold())
            embed.set_footer(text="Source ： Ahgang/知足常樂資料庫")
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ 找不到技能 **'{skill_name}'** 的相關物品。")

    except Exception as e:
        print(f"Prefix skill list error: {e}")
        await ctx.send("❌ 獲取技能清單時發生錯誤。")
