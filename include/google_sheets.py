import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json

def fetch_agents_sheet(service_account_info: dict, spreadsheet_id: str, sheet_name: str, local_csv_path: str):
    """
    Reads data from Google Sheet using service account credentials and saves to CSV.
    
    Args:
        service_account_info: dict from service account JSON
        spreadsheet_id: str, Google Sheet ID
        sheet_name: str, worksheet name
        local_csv_path: str, path to save CSV
    """
    #API scope definition
    scope = ['https://www.googleapis.com/auth/spreadsheets']

    # Authentication
    creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
    client = gspread.authorize(creds)

    # Open the sheet
    spreadsheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)

    # Get records and save CSV
    records = spreadsheet.get_all_records()
    df = pd.DataFrame(records)
    df.to_csv(local_csv_path, index=False)

    return local_csv_path
