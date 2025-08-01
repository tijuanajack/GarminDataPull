from garminconnect import Garmin
from pathlib import Path
import os, json
from datetime import datetime, timedelta
import pandas as pd

# ---------- helpers ----------
def safe_val(obj, *keys):
    """Walk nested dict keys safely; return None if any link is missing."""
    cur = obj
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur

# ---------- login ----------
def login(email, password, mfa=None):
    store = Path(__file__).resolve().parent / "data" / ".garminconnect"
    try:
        gc = Garmin()
        gc.login(str(store))
        print("✅ token login")
        return gc
    except Exception:
        gc = Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)
        res1, res2 = gc.login()
        if res1 == "needs_mfa":
            if not mfa:
                raise RuntimeError("MFA required but GARMIN_MFA_CODE not set")
            gc.resume_login(res2, mfa)
        gc.garth.dump(str(store))
        print("✅ fresh login, token stored")
        return gc

# ---------- row extractor ----------
def extract_row(d, date_str):
    bc   = d.get("body_composition", {}) or {}
    batt = d.get("body_battery", {})      or {}
    sl   = d.get("sleep", {})             or {}
    st   = d.get("stress", {})            or {}
    steps= d.get("steps", {})             or {}
    tr   = d.get("training_readiness", {})or {}

    weight   = safe_val(bc, "totalAverage", "weight") or bc.get("weight")
    body_fat = safe_val(bc, "totalAverage", "bodyFat") or bc.get("bodyFat")

    if isinstance(batt, list) and batt:
        body_battery = batt[0].get("bodyBatteryAvg")
    else:
        body_battery = (
            safe_val(batt, "bodyBatterySummary", "average")
            or batt.get("bodyBatteryAvg")
        )

    readiness = tr.get("trainingReadinessScore") or tr.get("score")

    # robust training status handling
    ts_raw = d.get("training_status")
    if isinstance(ts_raw, dict):
        training_status = safe_val(ts_raw, "trainingStatus", "statusType", "status")
    else:
        training_status = None  # list or empty/no status

    sleep_score = (
        safe_val(sl, "sleepScores", "overall", "value")
        or sl.get("overallSleepScore")
    )
    stress_lvl = (
        safe_val(st, "dailyStress", "score")
        or st.get("avgStressLevel")
    )

    return {
        "date":            date_str,
        "weight_kg":       round(weight / 1000, 2) if isinstance(weight, (int, float)) else None,
        "body_fat_%":      body_fat,
        "training_ready":  readiness,
        "training_status": training_status,
        "body_battery":    body_battery,
        "sleep_score":     sleep_score,
        "resting_hr":      safe_val(d.get("resting_hr", {}), "restingHeartRate"),
        "stress_level":    stress_lvl,
        "steps":           steps.get("totalSteps"),
    }

# ---------- main ----------
def main():
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]
    mfa = os.getenv("GARMIN_MFA_CODE")         # optional

    base = Path(__file__).resolve().parent
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    client = login(email, password, mfa)

    today = datetime.today().date()
    rows = []

    for offset in range(30):
        day = today - timedelta(days=offset)
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

            # Optional debug JSON – delete if you no longer need raw files
            dbg_file = data_dir / f"{day_str}.json"
            with open(dbg_file, "w") as f:
                json.dump(d, f, indent=2)

        except Exception as e:
            print(f"⚠️ {day_str}: {e}")

    df = pd.DataFrame(rows)
    out_csv   = data_dir / f"garmin_summary_{today}.csv"
    latest_csv= data_dir / "latest_summary.csv"
    df.to_csv(out_csv, index=False)
    df.to_csv(latest_csv, index=False)
    print(f"✅ wrote {out_csv.name} and latest_summary.csv")

if __name__ == "__main__":
    main()
