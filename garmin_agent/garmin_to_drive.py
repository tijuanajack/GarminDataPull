
from garminconnect import Garmin
from pathlib import Path
import os, json
from datetime import datetime, timedelta
import pandas as pd

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

    base = Path(__file__).resolve().parent
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    client = login_to_garmin(email, password, mfa)

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
        except Exception as e:
            print(f"⚠️  {day_str} failed: {e}")

    df = pd.DataFrame(rows)
    summary_csv = data_dir / f"garmin_summary_{today}.csv"
    latest_csv = data_dir / "latest_summary.csv"
    df.to_csv(summary_csv, index=False)
    df.to_csv(latest_csv, index=False)
    print(f"✅ Saved {summary_csv.name} and latest_summary.csv")

if __name__ == "__main__":
    main()
