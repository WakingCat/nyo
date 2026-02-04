import gspread

def inspect():
    gc = gspread.service_account(filename='credentials.json')
    # ID provided by the user
    sh = gc.open_by_key('1U7oMiVMWaBqBcxIzhdJdzKO4-LoME_gyAiMsw6nJDE0')
    worksheet = sh.worksheet("DATA")
    
    # Get just the first row to see headers
    headers = worksheet.row_values(1)
    print("Headers Found:")
    print(headers)
    
    print("\nInspecting problematic rows around 52099:")
    records = worksheet.get_all_records()
    total = len(records)
    start_idx = 52090
    end_idx = min(start_idx + 15, total)
    
    for i in range(start_idx, end_idx):
        print(f"Row {i+2}: {records[i]}")

if __name__ == "__main__":
    inspect()
