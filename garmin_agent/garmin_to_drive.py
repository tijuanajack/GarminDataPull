from garminconnect import Garmin
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import os, json

# ───────── helpers ─────────
def as_dict(x):       return x if isinstance(x, dict) else {}
def first(x):         return x[0] if isinstance(x, list) and x else {}
def safe(obj, *keys):
    cur = obj
    for k in keys:
        cur = as_dict(cur).get(k)
        if cur is None:
            return None
    return cur

def login(email, pwd, mfa):
    store = Path(__file__).parent / "data" / ".garminconnect"
    try:
        g = Garmin(); g.login(str(store)); return g
    except Exception:
        g = Garmin(email=email, password=pwd, is_cn=False, return_on_mfa=True)
        s1, s2 = g.login()
        if s1 == "needs_mfa":
            if not mfa: raise RuntimeError("MFA required but GARMIN_MFA_CODE not set")
            g.resume_login(s2, mfa)
        g.garth.dump(str(store)); return g

# ───────── extractor ─────────
def extract_row(raw, date_str):
    bc   = as_dict(raw.get("body_composition"))
    batt = raw.get("body_battery")
    batt = batt[0] if isinstance(batt, list) and batt else as_dict(batt)
    sl   = as_dict(raw.get("sleep"))
    st   = as_dict(raw.get("stress"))
    tr   = as_dict(raw.get("training_readiness"))
    steps= as_dict(raw.get("steps"))

    ts_raw = raw.get("training_status")
    ts_raw = as_dict(ts_raw)

    weight     = safe(bc, "totalAverage", "weight") or bc.get("weight")
    body_fat   = safe(bc, "totalAverage", "bodyFat") or bc.get("bodyFat")

    row = {
        "date": date_str,
        "weight_kg":        round(weight/1000,2) if isinstance(weight,(int,float)) else None,
        "body_fat_%":       body_fat,
        "training_ready":   tr.get("trainingReadinessScore") or tr.get("score") or safe(tr,"overallDTO","score"),
        "training_status":  safe(ts_raw,"trainingStatus","statusType","status"),
        "body_battery":     batt.get("bodyBatteryAvg") or safe(batt,"bodyBatterySummary","average"),
        "sleep_score":      safe(sl,"sleepScores","overall","value") or sl.get("overallSleepScore"),
        "resting_hr":       safe(raw.get("resting_hr",{}),"restingHeartRate"),
        "stress_level":     safe(st,"dailyStress","score") or st.get("avgStressLevel"),
        "respiration_avg":  safe(raw.get("resp",{}),"dailySummary","averageRespiration") \
                            or safe(first(sl.get("dailySleepDTO",{})),"averageRespirationValue"),
        "steps":            steps.get("totalSteps"),
        "activities": None  # fill below
    }

    # activities list
    acts = (
        raw.get("activity_stats",{}).get("bodyBatteryActivityEventList",[]) or
        raw.get("activity_stats",{}).get("bodyBatteryAutoActivityEventList",[])
    )
    if isinstance(acts,list):
        row["activities"] = ", ".join(
            f"{ev.get('activityType','').lower()}-{ev.get('shortFeedback','').upper()}"
            for ev in acts if ev.get("eventType")=="ACTIVITY"
        ) or None

    return row

# ───────── main ─────────
def main():
    email = os.environ["GARMIN_EMAIL"]
    pwd   = os.environ["GARMIN_PASSWORD"]
    mfa   = os.getenv("GARMIN_MFA_CODE")

    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    g = login(email, pwd, mfa)

    today = datetime.today().date()
    rows  = []

    for i in range(30):
        day = today - timedelta(days=i)
        ds  = day.isoformat()
        try:
            raw = {
                "activity_stats":     g.get_stats(ds),
                "body_composition":   g.get_body_composition(ds),
                "steps":              g.get_steps_data(ds),
                "training_readiness": g.get_training_readiness(ds),
                "body_battery":       g.get_body_battery(ds, ds),
                "training_status":    g.get_training_status(ds),
                "resting_hr":         g.get_rhr_day(ds),
                "sleep":              g.get_sleep_data(ds),
                "stress":             g.get_stress_data(ds),
                "resp":               g.get_respiration_data(ds),
            }
            rows.append(extract_row(raw, ds))
        except Exception as e:
            print(f"⚠️ {ds}: {e}")

    if not rows:
        raise RuntimeError("No rows extracted; check API responses.")

    df = pd.DataFrame(rows).sort_values("date")
    out_csv    = data_dir / f"garmin_summary_{today}.csv"
    latest_csv = data_dir / "latest_summary.csv"
    df.to_csv(out_csv, index=False)
    df.to_csv(latest_csv, index=False)
    print(f"✅ wrote {out_csv.name} and latest_summary.csv")

if __name__ == "__main__":
    main()
