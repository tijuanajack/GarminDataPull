
# garmin_agent/activity_export.py  v2
# Focus: reliable population of core metrics for run, trail_run, swim, hiit/strength, hike, walk
# Strategy: use get_activities_by_date for the window, then enrich with details; fall back to list summary when details missing

from garminconnect import Garmin
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pandas as pd, json, os, time

# ---------- helpers ----------
def as_dict(x):       return x if isinstance(x, dict) else {}
def first(x):         return x[0] if isinstance(x, list) and x else {}
def safe(d, *keys, default=None):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur

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

def iso_to_dt(s):
    if not s: return None
    s = s.replace("Z", "+00:00")
    try: return datetime.fromisoformat(s)
    except: return None

def pace_per_km(avg_speed_mps):
    return (1000.0/avg_speed_mps) if avg_speed_mps and avg_speed_mps>0 else None

def pace_per_mile(avg_speed_mps):
    return (1609.344/avg_speed_mps) if avg_speed_mps and avg_speed_mps>0 else None

def compact_laps_from_details(details: dict):
    # prefer lapDTOs from details if present
    laps = as_dict(details).get("lapDTOs") or []
    out = []
    for i, lap in enumerate(laps, 1):
        sd = as_dict(lap.get("summaryDTO", {}))
        out.append({
            "i": i,
            "dist_m": sd.get("distance"),
            "dur_s": sd.get("duration"),
            "avg_spd": sd.get("averageSpeed"),
            "avg_hr": sd.get("averageHR"),
            "gain_m": sd.get("elevationGain"),
        })
    return json.dumps(out, separators=(",", ":"), ensure_ascii=False) if out else None

def compact_splits(api, act_id):
    # fall back to split summaries to reduce payload
    try:
        ss = api.get_activity_split_summaries(act_id) or {}
    except Exception:
        ss = {}
    laps = as_dict(ss).get("lapDTOs") or []
    out = []
    for i, lap in enumerate(laps, 1):
        sd = as_dict(lap.get("summaryDTO", {}))
        out.append({
            "i": i,
            "dist_m": sd.get("distance"),
            "dur_s": sd.get("duration"),
            "avg_spd": sd.get("averageSpeed"),
            "avg_hr": sd.get("averageHR"),
            "gain_m": sd.get("elevationGain"),
        })
    return json.dumps(out, separators=(",", ":"), ensure_ascii=False) if out else None

def normalize_type(type_key: str):
    if not type_key:
        return None
    t = type_key.lower()
    # map common variants
    if t in ("running", "trail_running", "treadmill_running"):
        return t
    if t in ("walking",):
        return "walking"
    if t in ("hiking",):
        return "hiking"
    if t in ("hiit", "indoor_cardio", "cross_training", "strength_training"):
        return t
    if t in ("pool_swimming", "open_water_swimming", "swimming"):
        return t
    return t

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

    # pull activity list by date window to ensure we only request details we need
    try:
        act_list = g.get_activities_by_date(start_date.isoformat(), today.isoformat(), None) or []
    except Exception:
        # fallback to pagination
        act_list = []
        page = 0; size = 200
        while True:
            batch = g.get_activities(page, size) or []
            if not batch: break
            act_list += batch
            page += size
            # stop early if older than window
            last_dt = iso_to_dt(batch[-1].get("startTimeGMT"))
            if last_dt and last_dt.date() < start_date:
                break

    rows = []
    for a in act_list:
        start_gmt = a.get("startTimeGMT")
        dt = iso_to_dt(start_gmt)
        if not dt: 
            continue
        act_date = dt.date()
        if act_date < start_date:
            continue

        act_id = a.get("activityId")
        type_key_raw = safe(a, "activityType", "typeKey")
        type_key = normalize_type(type_key_raw)

        # details often missing fields, so fallback to list summary
        try:
            details = g.get_activity_details(act_id) or {}
        except Exception:
            details = {}
        det_summary = as_dict(details.get("summaryDTO", {}))
        list_summary = as_dict(a.get("summaryDTO", {}))
        summary = det_summary if det_summary else list_summary

        # aux endpoints best effort
        try:   weather = g.get_activity_weather(act_id) or {}
        except Exception: weather = {}
        try:   gear = g.get_activity_gear(act_id) or {}
        except Exception: gear = {}
        try:   evaln = g.get_activity_evaluation(act_id) or {}
        except Exception: evaln = {}

        # compact laps and splits
        laps_json = compact_laps_from_details(details)
        if laps_json is None:
            laps_json = compact_splits(g, act_id)

        avg_speed = summary.get("averageSpeed")
        base = {
            "date": act_date.isoformat(),
            "activity_id": act_id,
            "name": a.get("activityName"),
            "type_key": type_key or type_key_raw,
            "start_local": a.get("startTimeLocal"),
            "start_gmt": start_gmt,

            "elapsed_sec": summary.get("duration"),
            "moving_sec": summary.get("movingDuration"),
            "distance_m": summary.get("distance"),
            "avg_speed_mps": avg_speed,
            "avg_pace_sec_per_km": pace_per_km(avg_speed),
            "avg_pace_sec_per_mile": pace_per_mile(avg_speed),

            "avg_hr": summary.get("averageHR"),
            "max_hr": summary.get("maxHR"),
            "calories": summary.get("calories"),

            "training_effect": summary.get("trainingEffect"),
            "aerobic_te": summary.get("aerobicTrainingEffect"),
            "anaerobic_te": summary.get("anaerobicTrainingEffect"),

            "elev_gain_m": summary.get("elevationGain"),
            "elev_loss_m": summary.get("elevationLoss"),

            "device_name": safe(details, "deviceMetaDataDTO", "deviceName") or safe(a, "deviceMetaDataDTO", "deviceName"),
            "weather_temp_c": weather.get("temperature"),
            "weather_humidity": weather.get("humidity"),
            "weather_condition": weather.get("condition"),
            "gear": json.dumps(gear, separators=(",", ":"), ensure_ascii=False) if gear else None,

            "rpe": evaln.get("perceivedExertion"),
            "perceived_feel": evaln.get("perceivedFeeling"),

            "splits_json": laps_json,
            "notes": a.get("notes"),
        }

        extra = {}
        if type_key in ("running", "trail_running", "treadmill_running"):
            extra.update({
                "cadence_avg": summary.get("averageRunCadence") or summary.get("averageCadence"),
                "stride_len_m": summary.get("strideLength"),
                "avg_power_w": summary.get("averagePower"),
                "terrain_type": "trail" if type_key == "trail_running" else "road_treadmill",
            })
        if type_key == "walking":
            extra.update({
                "cadence_avg": summary.get("averageCadence"),
                "steps": summary.get("steps") or safe(list_summary, "steps"),
            })
        if type_key == "hiking":
            extra.update({
                "cadence_avg": summary.get("averageCadence"),
                "max_elev_m": summary.get("maxElevation"),
            })
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
                "strength_sets_json": json.dumps(strength_sets, separators=(",", ":"), ensure_ascii=False) if strength_sets else None,
            })
        if type_key in ("pool_swimming", "open_water_swimming", "swimming"):
            extra.update({
                "pool_length_m": summary.get("poolLength"),
                "total_lengths": summary.get("totalNumberOfLengths"),
                "total_strokes": summary.get("totalNumberOfStrokes"),
                "swolf_avg": summary.get("avgSwolf"),
                "stroke_counts_json": json.dumps(details.get("swimExerciseDTOs", []), separators=(",", ":"), ensure_ascii=False) if details.get("swimExerciseDTOs") else None,
                "pace_sec_per_100m": (100.0/avg_speed) if avg_speed else None,
            })

        row = {**base, **extra}
        rows.append(row)

    if not rows:
        raise RuntimeError("No activities in range. Check window or Garmin sync.")

    df = pd.DataFrame(rows).sort_values(["date", "start_local", "activity_id"])
    out = Path(__file__).parent / "data" / "latest_activity_summary.csv"
    df.to_csv(out, index=False)
    print(f"✅ saved {out.name} with {len(df)} activities over the last {days} days.")

if __name__ == "__main__":
    main()
