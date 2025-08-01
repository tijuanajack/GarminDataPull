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
            daily_data = {}

            def safe_get(name, func):
                try:
                    result = func()
                    daily_data[name] = result
                except Exception as e:
                    print(f"⚠️  Failed to get {name}: {e}")
                    daily_data[name] = None

            safe_get("activity_stats", lambda: client.get_stats(date_str))
            safe_get("body_composition", lambda: client.get_body_composition(date_str))
            safe_get("steps", lambda: client.get_steps_data(date_str))
            safe_get("heart_rate", lambda: client.get_heart_rates(date_str))
            safe_get("training_readiness", lambda: client.get_training_readiness(date_str))
            safe_get("body_battery", lambda: client.get_body_battery(date_str, date_str))
            safe_get("training_status", lambda: client.get_training_status(date_str))
            safe_get("resting_hr", lambda: client.get_rhr_day(date_str))
            safe_get("sleep", lambda: client.get_sleep_data(date_str))
            safe_get("stress", lambda: client.get_stress_data(date_str))
            safe_get("respiration", lambda: client.get_respiration_data(date_str))
            safe_get("spo2", lambda: client.get_spo2_data(date_str))
            safe_get("max_metrics", lambda: client.get_max_metrics(date_str))
            safe_get("hrv", lambda: client.get_hrv_data(date_str))
            safe_get("hill_score", lambda: client.get_hill_score(date_str, date_str))
            safe_get("endurance_score", lambda: client.get_endurance_score(date_str, date_str))
            safe_get("race_predictions", lambda: client.get_race_predictions())
            safe_get("all_day_stress", lambda: client.get_all_day_stress(date_str))
            safe_get("fitness_age", lambda: client.get_fitnessage_data(date_str))

            # Flatten and store only what we care about
            summary = {
                "date": date_str,
                "body_battery_avg": daily_data.get("body_battery", {}).get("bodyBatteryAverage", None),
                "readiness_score": daily_data.get("training_readiness", {}).get("readinessScore", None),
                "training_status": daily_data.get("training_status", {}).get("trainingStatus", None),
                "sleep_score": daily_data.get("sleep", {}).get("sleepScores", [{}])[0].get("overallScore", None),
                "stress_avg": daily_data.get("stress", {}).get("userStressAllDay", [{}])[0].get("averageStressLevel", None),
                "resting_hr": daily_data.get("resting_hr", {}).get("restingHeartRate", None),
                "vo2max": daily_data.get("max_metrics", {}).get("vo2MaxValue", None),
                "fitness_age": daily_data.get("fitness_age", {}).get("fitnessAge", None),
            }

            records.append(summary)

            json_file = out_json_dir / f"{date_str}.json"
            with open(json_file, "w") as f:
                json.dump(daily_data, f, indent=4)
            print(f"✅ Data saved for {date_str}.")

        except Exception as e:
            print(f"❌ Failed to pull data for {date_str}: {e}")

    df = pd.DataFrame(records)
    latest_csv = out_json_dir / f"garmin_summary_{today}.csv"
    df.to_csv(latest_csv, index=False)
    print(f"✅ Saved 30-day summary: {latest_csv}")

    # Save/update fixed latest filename
    fixed_csv = out_json_dir / "latest_summary.csv"
    df.to_csv(fixed_csv, index=False)
    print(f"📌 Updated latest_summary.csv")

if __name__ == "__main__":
    main()
