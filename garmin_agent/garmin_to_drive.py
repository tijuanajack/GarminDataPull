# garmin_agent/garmin_to_drive.py
from garminconnect import Garmin
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd, json, os

# ---------- helpers ----------
def as_dict(x):       return x if isinstance(x, dict) else {}
def first(x):         return x[0] if isinstance(x, list) and x else {}
def safe(obj, *keys):
    cur = obj
    for k in keys:
        cur = as_dict(cur).get(k, {})
    return cur or None

def login(email, pwd, mfa=None):
    store = Path(__file__).parent / "data" / ".garminconnect"
    try:
        g = Garmin(); g.login(str(store)); return g
    except Exception:
        g = Garmin(email=email, password=pwd, is_cn=False, return_on_mfa=True)
        s1, s2 = g.login()
        if s1 == "needs_mfa":
            if not mfa: raise RuntimeError("MFA required")
            g.resume_login(s2, mfa)
        g.garth.dump(str(store)); return g

# ---------- main ----------
def main():
    email = os.environ["GARMIN_EMAIL"]
    pwd   = os.environ["GARMIN_PASSWORD"]
    mfa   = os.getenv("GARMIN_MFA_CODE")
    g     = login(email, pwd, mfa)

    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.today().date()
    rows  = []

    for i in range(30):
        day = today - timedelta(days=i)
        ds  = day.isoformat()
        try:
            raw = {
                "activity_stats":   g.get_stats(ds),
                "body_composition": g.get_body_composition(ds),
                "steps":            g.get_steps_data(ds),
                "heart":            g.get_heart_rates(ds),
                "ready":            g.get_training_readiness(ds),
                "battery":          g.get_body_battery(ds, ds),
                "status":           g.get_training_status(ds),
                "rhr":              g.get_rhr_day(ds),
                "sleep":            g.get_sleep_data(ds),
                "stress":           g.get_stress_data(ds),
                "resp":             g.get_respiration_data(ds),
                "spo2":             g.get_spo2_data(ds),
                "max":              g.get_max_metrics(ds),
                "hrv":              g.get_hrv_data(ds),
                "hill":             g.get_hill_score(ds, ds),
                "endur":            g.get_endurance_score(ds, ds),
                "race":             g.get_race_predictions(),
                "allstress":        g.get_all_day_stress(ds),
                "fitage":           g.get_fitnessage_data(ds),
            }

            # --------- NEW → flatten any one-element lists ----------
            for k, v in raw.items():
                if isinstance(v, list):
                    raw[k] = v[0] if v else {}

            # --------- summary row (mirrors Collab logic) ----------
            ready_raw = raw["ready"] or {}
            row = {
                "date": ds,
                "readiness": ready_raw.get("trainingReadinessScore") or ready_raw.get("score"),
                "hrv":       safe(raw["hrv"], "hrvSummary", "lastNightAvg"),
                "rhr":       safe(raw["heart"], "restingHeartRate"),
                "sleep_hrs": round((safe(raw["sleep"], "dailySleepDTO", "sleepTimeSeconds") or 0)/3600,2),
                "steps":     safe(raw["activity_stats"], "totalSteps"),
                "stress_avg":  safe(raw["activity_stats"], "averageStressLevel"),
                "stress_dur":  round((safe(raw["activity_stats"], "stressDuration") or 0)/3600,2),
                "calories_active": safe(raw["activity_stats"], "activeKilocalories"),
                "bb_start":  safe(raw["activity_stats"], "bodyBatteryAtWakeTime"),
                "bb_end":    safe(raw["activity_stats"], "bodyBatteryMostRecentValue"),
                "bb_low":    safe(raw["activity_stats"], "bodyBatteryLowestValue"),
                "vo2max":    safe(raw["status"], "mostRecentVO2Max", "generic", "vo2MaxValue"),
                "fitness_age": safe(raw["fitage"], "fitnessAge"),
                # ─── average respiration ───
"respiration_avg": (
    (raw["resp"] or {}).get("dailySummary", {}).get("averageRespiration")      # normal endpoint
    or (raw["resp"] or {}).get("averageRespiration")                           # some devices
    or safe(first(raw["sleep"].get("dailySleepDTO", {})), "averageRespirationValue")  # sleep fallback
),
                "acute_training_load": safe(raw["status"], "mostRecentTrainingStatus", "latestTrainingStatusData", "3449644769", "acuteTrainingLoadDTO", "acwrStatus"),
                "training_need": safe(raw["status"], "mostRecentTrainingLoadBalance", "metricsTrainingLoadBalanceDTOMap", "3449644769", "trainingBalanceFeedbackPhrase"),
            }

            # ---------- activities list (handles both event lists) ----------
            acts1 = raw["activity_stats"].get("bodyBatteryActivityEventList", [])
            acts2 = raw["activity_stats"].get("bodyBatteryAutoActivityEventList", [])
            events = []

            if isinstance(acts1, list):
                events.extend(acts1)
            if isinstance(acts2, list):
                events.extend(acts2)

            pairs = [
                f"{ev.get('activityType','').lower()}-{ev.get('shortFeedback','').upper()}"
                for ev in events
                if ev.get("eventType") == "ACTIVITY"
            ]

            row["activities"] = ", ".join(pairs) if pairs else None

            # body-comp extras
            bc_avg = as_dict(raw["body_composition"]).get("totalAverage", {})
            if bc_avg:
                row.update({
                    "weight":       round(bc_avg.get("weight",0)/1000,2) if bc_avg.get("weight") else None,
                    "percent_fat":  bc_avg.get("bodyFat"),
                    "muscle_mass":  round(bc_avg.get("muscleMass",0)/1000,2) if bc_avg.get("muscleMass") else None,
                    "bone_mass":    round(bc_avg.get("boneMass",0)/1000,2) if bc_avg.get("boneMass") else None,
                    "bmi":          round(bc_avg.get("bmi",0),2) if bc_avg.get("bmi") else None,
                    "visceral_fat": bc_avg.get("visceralFat"),
                })

            rows.append(row)

        except Exception as e:
            print(f"⚠️ {ds}: {e}")

    if not rows:
        raise RuntimeError("No rows extracted; check API responses.")

    df = pd.DataFrame(rows).sort_values("date")
    out = data_dir / f"garmin_summary_{today}.csv"
    df.to_csv(out, index=False)
    df.to_csv(data_dir / "latest_summary.csv", index=False)
    print(f"✅ saved {out.name} and latest_summary.csv")

if __name__ == "__main__":
    main()
