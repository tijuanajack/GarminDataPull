from garminconnect import Garmin
from pathlib import Path
import os
import json
from datetime import datetime, timedelta
import pandas as pd

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_to_drive(file_path, folder_id, creds_json):
    credentials = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    service = build('drive', 'v3', credentials=credentials)

    file_metadata = {
        'name': Path(file_path).name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, resumable=True)

    uploaded = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print(f"📤 Uploaded to Google Drive with file ID: {uploaded.get('id')}")

def login_to_garmin(email, password, mfa=None):
    folder_path = Path(__file__).resolve().parent / "data"
    tokenstore = folder_path / ".garminconnect"

    print(f"🔍 Checking for token at: {tokenstore}")
    if not (tokenstore / "oauth1_token.json").exists():
        print("❌ oauth1_token.json not found at expected path.")
    else:
        print("✅ Found oauth1_token.json!")

    try:
        client = Garmin()
        client.login(str(tokenstore))
        print("✅ Logged in using saved token.")
        return client
    except Exception as e:
        print(f"⚠️  Token login failed: {e}. Attempting full login...")

    try:
        client = Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)
        result1, result2 = client.login()
        if result1 == "needs_mfa":
            if mfa is None:
                raise ValueError("MFA code required but not provided.")
            client.resume_login(result2, mfa)
        client.garth.dump(str(tokenstore))
        print("✅ Logged in with credentials and saved token.")
        return client
    except Exception as e:
        print("❌ Garmin login failed:", e)
        raise

def main():
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    mfa = os.environ.get("GARMIN_MFA_CODE")
    drive_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    drive_creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not all([email, password]):
        raise RuntimeError("GARMIN_EMAIL and GARMIN_PASSWORD must be set as environment variables.")

    client = login_to_garmin(email, password, mfa)

    folder_path = Path(__file__).resolve().parent / "data"
    out_json_dir = folder_path
    out_json_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.today().date()
    days_back = 30
    summary_records = []

    for i in range(days_back):
        date_obj = today - timedelta(days=i)
        date_str = date_obj.isoformat()
        print(f"\n📅 Pulling data for {date_str}...")

        try:
            steps = client.get_steps_data(date_str)
            sleep = client.get_sleep_data(date_str)
            stress = client.get_stress_data(date_str)
            readiness = client.get_training_readiness(date_str)
            battery = client.get_body_battery(date_str, date_str)

            record = {
                "date": date_str,
                "steps": steps[0].get("steps") if steps else None,
                "sleep_score": sleep.get("sleepScores", {}).get("overall", None),
                "stress_level": stress[0].get("stressLevel") if isinstance(stress, list) and stress else None,
                "readiness_score": readiness.get("score", None),
                "body_battery_avg": battery.get("bodyBatterySummary", {}).get("averageBodyBattery", None)
            }
            summary_records.append(record)

        except Exception as e:
            print(f"❌ Failed to pull data for {date_str}: {e}")

    df = pd.DataFrame(summary_records)
    csv_file = out_json_dir / f"garmin_summary_{today}.csv"
    df.to_csv(csv_file, index=False)
    print(f"✅ Saved 30-day summary: {csv_file}")

    latest_summary = out_json_dir / "latest_summary.csv"
    df.to_csv(latest_summary, index=False)
    print("📌 Updated latest_summary.csv")

    if drive_folder_id and drive_creds_json:
        upload_to_drive(str(csv_file), drive_folder_id, drive_creds_json)

if __name__ == "__main__":
    main()
