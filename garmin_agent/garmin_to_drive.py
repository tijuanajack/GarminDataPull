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

def extract_summary_data(date_str, data):
    try:
        return {
            "date": date_str,
            "weight": data["body_composition"].get("weight"),
            "body_fat": data["body_composition"].get("bodyFat"),
            "training_readiness": data["training_readiness"].get("trainingReadinessScore"),
            "training_status": data["training_status"]["trainingStatus"].get("statusType", {}).get("status") if isinstance(data["training_status"], dict) else None,
            "body_battery": data["body_battery"][0].get("bodyBatteryAvg") if isinstance(data["body_battery"], list) and data["body_battery"] else None,
            "sleep_score": data["sleep"].get("sleepScores", {}).get("overall", {}).get("value"),
            "resting_hr": data["resting_hr"].get("restingHeartRate"),
            "stress_level": data["stress"].get("dailyStress", {}).get("score")
        }
    except Exception as e:
        print(f"⚠️ Error extracting summary for {date_str}: {e}")
        return None

def main():
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    mfa = os.environ.get("GARMIN_MFA_CODE")

    if not all([email, password]):
        raise RuntimeError("GARMIN_EMAIL and GARMIN_PASSWORD must be set as environment variables.")

    client = login_to_garmin(email, password, mfa)

    folder_path = Path(__file__).resolve().parent / "data"
    folder_path.mkdir(parents=True, exist_ok=True)

    today = datetime.today().date()
    days_back = 30
    summary = []

    for i in range(days_back):
        date_obj = today - timedelta(days=i)
        date_str = date_obj.isoformat()
        print(f"\n📅 Pulling data for {date_str}...")

        try:
            data = {
                "activity_stats": client.get_stats(date_str),
                "body_composition": client.get_body_composition(date_str),
                "steps": client.get_steps_data(date_str),
                "heart_rate": client.get_heart_rates(date_str),
                "training_readiness": client.get_training_readiness(date_str),
                "body_battery": client.get_body_battery(date_str, date_str),
                "training_status": client.get_training_status(date_str),
                "resting_hr": client.get_rhr_day(date_str),
                "sleep": client.get_sleep_data(date_str),
                "stress": client.get_stress_data(date_str),
                "respiration": client.get_respiration_data(date_str),
                "spo2": client.get_spo2_data(date_str),
                "max_metrics": client.get_max_metrics(date_str),
                "hrv": client.get_hrv_data(date_str),
                "hill_score": client.get_hill_score(date_str, date_str),
                "endurance_score": client.get_endurance_score(date_str, date_str),
                "race_predictions": client.get_race_predictions(),
                "all_day_stress": client.get_all_day_stress(date_str),
                "fitness_age": client.get_fitnessage_data(date_str)
            }

            json_file = folder_path / f"{date_str}.json"
            with open(json_file, "w") as f:
                json.dump(data, f, indent=4)
            print(f"✅ Data saved for {date_str}.")

            row = extract_summary_data(date_str, data)
            if row:
                summary.append(row)

        except Exception as e:
            print(f"❌ Failed to pull data for {date_str}: {e}")

    df = pd.DataFrame(summary)
    summary_csv = folder_path / f"garmin_summary_{today.isoformat()}.csv"
    df.to_csv(summary_csv, index=False)
    print(f"✅ Saved 30-day summary: {summary_csv}")

    latest_csv = folder_path / "latest_summary.csv"
    df.to_csv(latest_csv, index=False)
    print("📌 Updated latest_summary.csv")

if __name__ == "__main__":
    main()
