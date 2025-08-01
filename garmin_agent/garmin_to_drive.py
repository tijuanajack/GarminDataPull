from garminconnect import Garmin
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import os, json

# ──────────────────── helpers ────────────────────
def safe_val(obj, *keys):
    """Safely walk nested dict keys; return None if any part missing."""
    cur = obj
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur

def first(x):
    """Return first element of list or {}."""
    return x[0] if isinstance(x, list) and x else {}

def login(email, pwd, mfa):
    store = Path(__file__).parent / "data" / ".garminconnect"
    try:
        g = Garmin(); g.login(str(store)); return g          # token OK
    except Exception:
        g = Garmin(email=email, password=pwd, is_cn=False, return_on_mfa=True)
        s1, s2 = g.login()
        if s1 == "needs_mfa":
            if not mfa: raise RuntimeError("MFA required but GARMIN_MFA_CODE not set")
            g.resume_login(s2, mfa)
        g.garth.dump(str(store)); return g

# ──────────────────── extractor ────────────────────
def extract_row(d, date_str):
    bc  = d.get("body_composition", {}) or {}
    batt= d.get("body_battery", {})     or {}
    sl  = d.get("sleep", {})            or {}
    st  = d.get("stress", {})           or {}
    tr  = d.get("training_readiness",{})or {}
    steps = d.get("steps", {})          or {}

    weight     = safe_val(bc, "totalAverage", "weight") or bc.get("weight")
    body_fat   = safe_val(bc, "totalAverage", "bodyFat") or bc.get("bodyFat")

    if isinstance(batt, list) and batt:
        body_battery = batt[0].get("bodyBatteryAvg")
    else:
        body_battery = (
            safe_val(batt, "bodyBatterySummary", "average")
            or batt.get("bodyBatteryAvg")
        )

    readiness = (
        tr.get("trainingReadinessScore")
        or tr.get("score")
        or safe_val(tr, "overallDTO", "score")
    )

    ts_raw = d.get("training_status")
    training_status = (
        safe_val(ts_raw, "trainingStatus", "statusType", "status")
        if isinstance(ts_raw, dict) else None
    )

    # respiration average: dailySummary or sleep fallback
    resp_raw = d.get("resp")
    respiration_avg = None
    if isinstance(resp_raw, dict):
        respiration_avg = safe_val(resp_raw, "dailySummary", "averageRespiration")
    if respiration_avg is None:
        respiration_avg = safe_val(first(sl.get("dailySleepDTO", {})),
                                   "averageRespirationValue")

    # activities list from either bodyBattery list
    acts_src = (
        d.get("activity_stats", {}).get("bodyBatteryActivityEventList", [])
        or d.get("activity_stats", {}).get("bodyBatteryAutoActivityEventList", [])
    )
    pairs = []
    if isinstance(acts_src, list):
        for ev in acts_src:
            if ev.get("eventType") == "ACTIVITY":
                pairs.append(
                    f"{ev.get('activityType','').lower()}-{ev.get('shortFeedback','').upper()}"
                )
    activities = ", ".join(pairs) if pairs else None

    return {
        "date":             date_str,
        "weight_kg":        round(weight / 1000, 2) if isinstance(weight, (int, float)) else None,
        "body_fat_%":       body_fat,
        "training_ready":   readiness,
        "training_status":  training_status,
        "body_battery":     body_battery,
        "sleep_score":      safe_val(sl, "sleepScores", "overall", "value") or sl.get("overallSleepScore"),
        "resting_hr":       safe_val(d.get("resting_hr", {}), "restingHeartRate"),
        "stress_level":     safe_val(st, "dailyStress", "score") or st.get("avgStressLevel"),
        "respiration_avg":  respiration_avg,
        "steps":            steps.get("totalSteps"),
        "activities":       activities,
    }

# ──────────────────── main ────────────────────
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
        print(f"📅 {ds}")
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

    df = pd.DataFrame(rows).sort_values("date")
    out_csv    = data_dir / f"garmin_summary_{today}.csv"
    latest_csv = data_dir / "latest_summary.csv"
    df.to_csv(out_csv, index=False)
    df.to_csv(latest_csv, index=False)
    print(f"✅ wrote {out_csv.name} and latest_summary.csv")

if __name__ == "__main__":
    main()
