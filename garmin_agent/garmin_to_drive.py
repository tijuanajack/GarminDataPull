
from garminconnect import Garmin
from pathlib import Path
import os
import json
from datetime import datetime, timedelta
import pandas as pd

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

    if not all([email, password]):
        raise RuntimeError("GARMIN_EMAIL and GARMIN_PASSWORD must be set as environment variables.")

    client = login_to_garmin(email, password, mfa)

    folder_path = Path(__file__).resolve().parent / "data"
    out_json_dir = folder_path
    out_json_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.today().date()
    days_back = 30
    records = []

    for i in range(days_back):
        date_obj = today - timedelta(days=i)
        date_str = date_obj.isoformat()
        print(f"\n📅 Pulling data for {date_str}...")

        try:
            daily_data = {
                "date": date_str,
                "readiness": client.get_training_readiness(date_str).get("trainingReadinessScore", 0),
                "body_battery_avg": client.get_body_battery(date_str, date_str).get("bodyBatteryAverage", 0),
                "sleep_score": client.get_sleep_data(date_str).get("sleepScores", [{}])[0].get("overall", 0),
                "stress_avg": client.get_stress_data(date_str).get("avgStressLevel", 0),
                "resting_hr": client.get_rhr_day(date_str).get("restingHeartRate", 0),
                "steps": client.get_steps_data(date_str).get("totalSteps", 0),
            }
            records.append(daily_data)
            print(f"✅ Data saved for {date_str}.")

        except Exception as e:
            print(f"❌ Failed to pull data for {date_str}: {e}")

    df = pd.DataFrame(records)
    out_csv = out_json_dir / f"garmin_summary_{today.isoformat()}.csv"
    df.to_csv(out_csv, index=False)
    print(f"\n✅ Summary saved to: {out_csv}")

if __name__ == "__main__":
    main()
