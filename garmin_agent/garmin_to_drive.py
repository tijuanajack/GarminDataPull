
from garminconnect import Garmin
from pathlib import Path
import os, json
from datetime import datetime, timedelta
import pandas as pd

<<<<<<< HEAD
# ---------- helpers ----------
def safe_val(obj, *keys):
    curr = obj
    for k in keys:
        if isinstance(curr, dict) and k in curr:
            curr = curr[k]
        else:
            return None
    return curr

# ---------- login ----------
=======
>>>>>>> 89fea6ce83266df174acaf6df8ef1d951d24b562
def login_to_garmin(email, password, mfa=None):
    folder = Path(__file__).resolve().parent / "data"
    tokenstore = folder / ".garminconnect"
    if (tokenstore / "oauth1_token.json").exists():
        print("✅ Found saved token; using it")
        client = Garmin()
        client.login(str(tokenstore))
        return client

    print("ℹ️ Saved token missing or invalid, doing full login")
    client = Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)
    result1, result2 = client.login()
    if result1 == "needs_mfa":
        if mfa is None:
            raise RuntimeError("MFA required but GARMIN_MFA_CODE not set")
        client.resume_login(result2, mfa)
    client.garth.dump(str(tokenstore))
    return client

<<<<<<< HEAD
# ---------- summary ----------
def extract_row(d, date_str):
    return {
        "date": date_str,
        "weight":              safe_val(d.get("body_composition", {}), "weight"),
        "body_fat":            safe_val(d.get("body_composition", {}), "bodyFat"),
        "training_readiness":  safe_val(d.get("training_readiness", {}), "trainingReadinessScore"),
        "training_status":     safe_val(d.get("training_status", {}), "trainingStatus", "statusType", "status"),
        "body_battery_avg":    d.get("body_battery")[0].get("bodyBatteryAvg") if isinstance(d.get("body_battery"), list) and d["body_battery"] else None,
        "sleep_score":         safe_val(d.get("sleep", {}), "sleepScores", "overall", "value"),
        "resting_hr":          safe_val(d.get("resting_hr", {}), "restingHeartRate"),
        "stress_level":        safe_val(d.get("stress", {}), "dailyStress", "score"),
        "steps":               safe_val(d.get("steps", {}), "totalSteps")
    }

# ---------- main ----------
def main():
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]
    mfa = os.getenv("GARMIN_MFA_CODE")
=======
def extract_summary_data(date_str, data):
    try:
        return {
            "date": date_str,
            "weight": data.get("body_composition", {}).get("weight"),
            "body_fat": data.get("body_composition", {}).get("bodyFat"),
            "training_readiness": data.get("training_readiness", {}).get("trainingReadinessScore"),
            "training_status": (
                data.get("training_status", {}).get("trainingStatus", {}).get("statusType", {}).get("status")
                if isinstance(data.get("training_status"), dict)
                else None
            ),
            "body_battery": (
                data.get("body_battery")[0].get("bodyBatteryAvg")
                if isinstance(data.get("body_battery"), list) and data.get("body_battery")
                else None
            ),
            "sleep_score": (
                data.get("sleep", {}).get("sleepScores", {}).get("overall", {}).get("value")
                if isinstance(data.get("sleep"), dict)
                else None
            ),
            "resting_hr": data.get("resting_hr", {}).get("restingHeartRate"),
            "stress_level": (
                data.get("stress", {}).get("dailyStress", {}).get("score")
                if isinstance(data.get("stress"), dict)
                else None
            )
        }
    except Exception as e:
        print(f"⚠️ Error extracting summary for {date_str}: {e}")
        return None


def main():
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    mfa = os.environ.get("GARMIN_MFA_CODE")
>>>>>>> 89fea6ce83266df174acaf6df8ef1d951d24b562

    base = Path(__file__).resolve().parent
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    client = login_to_garmin(email, password, mfa)

<<<<<<< HEAD
    today = datetime.today().date()
    rows = []
    for delta in range(30):
        day = today - timedelta(days=delta)
        day_str = day.isoformat()
        print(f"📅 {day_str}")
        try:
            d = {
                "body_composition":  client.get_body_composition(day_str),
                "training_readiness":client.get_training_readiness(day_str),
                "training_status":   client.get_training_status(day_str),
                "body_battery":      client.get_body_battery(day_str, day_str),
                "sleep":             client.get_sleep_data(day_str),
                "resting_hr":        client.get_rhr_day(day_str),
                "stress":            client.get_stress_data(day_str),
                "steps":             client.get_steps_data(day_str),
            }
            rows.append(extract_row(d, day_str))
=======
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

>>>>>>> 89fea6ce83266df174acaf6df8ef1d951d24b562
        except Exception as e:
            print(f"⚠️  {day_str} failed: {e}")

<<<<<<< HEAD
    df = pd.DataFrame(rows)
    summary_csv = data_dir / f"garmin_summary_{today}.csv"
    latest_csv = data_dir / "latest_summary.csv"
    df.to_csv(summary_csv, index=False)
    df.to_csv(latest_csv, index=False)
    print(f"✅ Saved {summary_csv.name} and latest_summary.csv")
=======
    df = pd.DataFrame(summary)
    summary_csv = folder_path / f"garmin_summary_{today.isoformat()}.csv"
    df.to_csv(summary_csv, index=False)
    print(f"✅ Saved 30-day summary: {summary_csv}")

    latest_csv = folder_path / "latest_summary.csv"
    df.to_csv(latest_csv, index=False)
    print("📌 Updated latest_summary.csv")
>>>>>>> 89fea6ce83266df174acaf6df8ef1d951d24b562

if __name__ == "__main__":
    main()
