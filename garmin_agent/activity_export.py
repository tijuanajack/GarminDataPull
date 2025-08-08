import os
import json
import pandas as pd
from datetime import datetime, timedelta, timezone
from garminconnect import Garmin

# ---------- config ----------
DAYS = int(os.getenv("DAYS_ACTIVITIES", "30"))  # how many days of activities to export
EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")

# ---------- utils ----------
def safe(d, *keys, default=None):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur

def to_json(obj):
    try:
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return None

def iso_to_date(iso):
    if not iso:
        return None
    # Garmin returns "2025-08-06T10:50:00.0" or "...Z"
    iso = iso.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso)
    except Exception:
        return None

def pace_per_km(avg_speed_mps):
    if not avg_speed_mps or avg_speed_mps <= 0:
        return None
    return 1000.0 / avg_speed_mps  # seconds per km

def pace_per_mile(avg_speed_mps):
    if not avg_speed_mps or avg_speed_mps <= 0:
        return None
    return 1609.344 / avg_speed_mps  # seconds per mile

# ---------- main ----------
def main():
    if not EMAIL or not PASSWORD:
        raise RuntimeError("Set GARMIN_EMAIL and GARMIN_PASSWORD env vars.")

    g = Garmin(EMAIL, PASSWORD)
    g.login()

    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=DAYS)

    # pull activities with pagination until we pass window
    page_start = 0
    page_size = 200  # big page to reduce calls
    rows = []

    while True:
        acts = g.get_activities(page_start, page_size) or []
        if not acts:
            break

        for a in acts:
            start_gmt = a.get("startTimeGMT")
            dt = iso_to_date(start_gmt)
            if not dt:
                continue
            act_date = dt.date()
            if act_date < start_date:
                # since list is reverse chronological, we can stop outer loops
                acts = []
                break

            act_id = a.get("activityId")
            type_key = safe(a, "activityType", "typeKey", default="unknown")

            # filter to your primaries; still include everything but enrich for these
            # primaries: running, trail_running, swimming, hiit/strength, hiking, walking
            # Garmin type keys vary; we branch on the ones you care about
            # fetch details and aux endpoints
            try:
                details = g.get_activity_details(act_id) or {}
            except Exception:
                details = {}
            summary = safe(details, "summaryDTO", default={})

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
            laps = safe(details, "lapDTOs", default=[])

            # base fields common to all
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

                "weather_temp_c": safe(weather, "temperature"),
                "weather_humidity": safe(weather, "humidity"),
                "weather_condition": safe(weather, "condition"),

                "device_name": safe(details, "deviceMetaDataDTO", "deviceName"),
                "gear": to_json(gear) if gear else None,

                "rpe": safe(evaln, "perceivedExertion"),
                "perceived_feel": safe(evaln, "perceivedFeeling"),

                "splits_json": to_json(splits or split_summ),
                "laps_json": to_json(laps),
                "notes": a.get("notes"),
            }

            # type specific enrichments
            extra = {}
            # running family
            if type_key in ("running", "trail_running", "treadmill_running"):
                extra.update({
                    "cadence_avg": summary.get("averageRunCadence") or summary.get("averageCadence"),
                    "stride_len_m": summary.get("strideLength"),
                    "avg_power_w": summary.get("averagePower"),
                    "terrain_type": "trail" if type_key == "trail_running" else "road/treadmill",
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

            # hiit / strength / cross
            if type_key in ("hiit", "indoor_cardio", "cross_training", "strength_training"):
                strength_sets = []
                if type_key == "strength_training":
                    try:
                        strength_sets = g.get_activity_exercise_sets(act_id) or []
                    except Exception:
                        strength_sets = []
                extra.update({
                    "sets_count": safe(summary, "numberOfSets"),
                    "total_reps": safe(summary, "totalReps"),
                    "total_weight_kg": safe(summary, "totalWeightLifted"),
                    "strength_sets_json": to_json(strength_sets) if strength_sets else None,
                })

            # swimming (pool or open water)
            if type_key in ("pool_swimming", "open_water_swimming", "swimming"):
                extra.update({
                    "pool_length_m": summary.get("poolLength"),
                    "total_lengths": summary.get("totalNumberOfLengths"),
                    "total_strokes": summary.get("totalNumberOfStrokes"),
                    "swolf_avg": summary.get("avgSwolf"),
                    "stroke_counts_json": to_json(safe(details, "swimExerciseDTOs", default=[])),
                    "pace_sec_per_100m": (100.0 / avg_speed) if avg_speed else None,
                })

            row = {**base, **extra}
            rows.append(row)

        if not acts:
            break

        page_start += page_size

    if not rows:
        raise RuntimeError("No recent activities found. Increase DAYS_ACTIVITIES or check Garmin sync.")

    df = pd.DataFrame(rows).sort_values(["date", "start_local", "activity_id"])
    df.to_csv("latest_activity_summary.csv", index=False)
    print(f"Saved latest_activity_summary.csv with {len(df)} activities over the last {DAYS} days.")

if __name__ == "__main__":
    main()
