# garmin_agent/activity_export.py
from garminconnect import Garmin
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pandas as pd, json, os

# ---------- helpers ----------
def as_dict(x):       return x if isinstance(x, dict) else {}
def first(x):         return x[0] if isinstance(x, list) and x else {}
def safe(obj, *keys, default=None):
    cur = obj
    for k in keys:
        if isinstance(cur, dict):
            cur = cur.get(k, {})
        else:
            return default
    return cur if cur not in ({}, None) else default

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

def iso_to_dt(iso_str):
    if not iso_str:
        return None
    # Garmin returns "YYYY-MM-DDTHH:MM:SS.s" maybe with Z
    iso_str = iso_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_str)
    except Exception:
        return None

def pace_sec_per_km(avg_speed_mps):
    if not avg_speed_mps or avg_speed_mps <= 0:
        return None
    return 1000.0 / avg_speed_mps

def pace_sec_per_mile(avg_speed_mps):
    if not avg_speed_mps or avg_speed_mps <= 0:
        return None
    return 1609.344 / avg_speed_mps

def to_json(obj):
    try:
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return None

# ---------- main ----------
def main():
    email = os.environ["GARMIN_EMAIL"]
    pwd   = os.environ["GARMIN_PASSWORD"]
    mfa   = os.getenv("GARMIN_MFA_CODE")
    g     = login(email, pwd, mfa)

    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    days = int(os.getenv("DAYS_ACTIVITIES", "30"))
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=days)

    rows = []
    page = 0
    page_size = 200

    while True:
        try:
            acts = g.get_activities(page, page_size) or []
        except Exception as e:
            print(f"⚠️ get_activities page {page}: {e}")
            break

        if not acts:
            break

        stop = False
        for a in acts:
            start_gmt = a.get("startTimeGMT")
            start_dt = iso_to_dt(start_gmt)
            if not start_dt:
                continue
            act_date = start_dt.date()
            if act_date < start_date:
                stop = True
                break

            act_id = a.get("activityId")
            type_key = safe(a, "activityType", "typeKey")

            # pull details with guards
            try:
                details = g.get_activity_details(act_id) or {}
            except Exception:
                details = {}
            summary = as_dict(details.get("summaryDTO", {}))

            try:
                weather = g.get_activity_weather(act_id) or {}
            except Exception:
                weather = {}
            try:
                gear = g.get_activity_gear(act_id) or {}
            except Exception:
                gear = {}
            try:
                evaln = g.get_activity_evaluation(act_id) or {}
            except Exception:
                evaln = {}
            try:
                splits = g.get_activity_splits(act_id) or {}
            except Exception:
                splits = {}
            try:
                split_summ = g.get_activity_split_summaries(act_id) or {}
            except Exception:
                split_summ = {}
            laps = details.get("lapDTOs", [])

            avg_speed = summary.get("averageSpeed")
            base = {
                "date": act_date.isoformat(),
                "activity_id": act_id,
                "name": a.get("activityName"),
                "type_key": type_key,
                "start_local": a.get("startTimeLocal"),
                "start_gmt": start_gmt,

                "elapsed_sec": summary.get("duration"),
                "moving_sec": summary.get("movingDuration"),
                "distance_m": summary.get("distance"),
                "avg_speed_mps": avg_speed,
                "avg_pace_sec_per_km": pace_sec_per_km(avg_speed),
                "avg_pace_sec_per_mile": pace_sec_per_mile(avg_speed),

                "avg_hr": summary.get("averageHR"),
                "max_hr": summary.get("maxHR"),
                "calories": summary.get("calories"),

                "training_effect": summary.get("trainingEffect"),
                "aerobic_te": summary.get("aerobicTrainingEffect"),
                "anaerobic_te": summary.get("anaerobicTrainingEffect"),

                "elev_gain_m": summary.get("elevationGain"),
                "elev_loss_m": summary.get("elevationLoss"),

                "device_name": safe(details, "deviceMetaDataDTO", "deviceName"),
                "weather_temp_c": weather.get("temperature"),
                "weather_humidity": weather.get("humidity"),
                "weather_condition": weather.get("condition"),
                "gear": to_json(gear) if gear else None,

                "rpe": evaln.get("perceivedExertion"),
                "perceived_feel": evaln.get("perceivedFeeling"),

                "splits_json": to_json(splits or split_summ),
                "laps_json": to_json(laps),
                "notes": a.get("notes"),
            }

            extra = {}
            # running family including trail and treadmill
            if type_key in ("running", "trail_running", "treadmill_running"):
                extra.update({
                    "cadence_avg": summary.get("averageRunCadence") or summary.get("averageCadence"),
                    "stride_len_m": summary.get("strideLength"),
                    "avg_power_w": summary.get("averagePower"),
                    "terrain_type": "trail" if type_key == "trail_running" else "road_treadmill",
                })
            # walking
            if type_key == "walking":
                extra.update({
                    "cadence_avg": summary.get("averageCadence"),
                    "steps": summary.get("steps"),
                })
            # hiking
            if type_key == "hiking":
                extra.update({
                    "cadence_avg": summary.get("averageCadence"),
                    "max_elev_m": summary.get("maxElevation"),
                })
            # hiit or strength or cross training
            if type_key in ("hiit", "indoor_cardio", "cross_training", "strength_training"):
                strength_sets = []
                if type_key == "strength_training":
                    try:
                        strength_sets = g.get_activity_exercise_sets(act_id) or []
                    except Exception:
                        strength_sets = []
                extra.update({
                    "sets_count": summary.get("numberOfSets"),
                    "total_reps": summary.get("totalReps"),
                    "total_weight_kg": summary.get("totalWeightLifted"),
                    "strength_sets_json": to_json(strength_sets) if strength_sets else None,
                })
            # swimming
            if type_key in ("pool_swimming", "open_water_swimming", "swimming"):
                extra.update({
                    "pool_length_m": summary.get("poolLength"),
                    "total_lengths": summary.get("totalNumberOfLengths"),
                    "total_strokes": summary.get("totalNumberOfStrokes"),
                    "swolf_avg": summary.get("avgSwolf"),
                    "stroke_counts_json": to_json(details.get("swimExerciseDTOs", [])),
                    "pace_sec_per_100m": (100.0 / avg_speed) if avg_speed else None,
                })

            row = {**base, **extra}
            rows.append(row)

        if stop:
            break
        page += page_size

    if not rows:
        raise RuntimeError("No recent activities found. Increase DAYS_ACTIVITIES or check Garmin sync.")

    df = pd.DataFrame(rows).sort_values(["date", "start_local", "activity_id"])
    out = data_dir / "latest_activity_summary.csv"
    df.to_csv(out, index=False)
    print(f"✅ saved {out.name} with {len(df)} activities over the last {days} days.")

if __name__ == "__main__":
    main()
