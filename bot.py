def fetch_item_data(query_name: str):
    try:
        df = pd.read_csv(CSV_URL)
        df.columns = df.columns.str.strip()
        
        target = query_name.strip().lower()

        # Search match against English 'Item' OR Chinese 'Item_CN'
        matches = df[
            (df['Item'].astype(str).str.strip().str.lower() == target) |
            (df['Item_CN'].astype(str).str.strip().str.lower() == target)
        ]
        
        if not matches.empty:
            row = matches.iloc[0]
            # Fallback to English item name if Item_CN is empty
            cn_name = str(row['Item_CN']) if 'Item_CN' in row and pd.notna(row['Item_CN']) else str(row['Item'])
            
            return {
                "found": True,
                "work_skill": str(row['WorkSkill']),
                "item": str(row['Item']),
                "item_cn": cn_name,
                "level": str(row['Level']),
                "exp": str(row['Exp']),
                "location": str(row['Location'])
            }
    except Exception as e:
        print(f"Error fetching sheet data: {e}")
    
    return {"found": False}
