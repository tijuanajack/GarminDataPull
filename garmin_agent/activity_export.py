
# garmin_agent/activity_export.py  v3 — aligned to your payloads
# Primary source: get_activities_by_date() list objects (your account does NOT include summaryDTO there)
# Avoids depending on get_activity_details(); uses list fields + splitSummaries directly.

from pathlib import Path
from datetime import datetime, timedelta, timezone
import os
import json

import pandas as pd

from auth import load_local_env, login

# ---------- helpers ----------
def iso_to_dt(s):
    if not s: return None
    s = s.replace("Z", "+00:00")
    try: return datetime.fromisoformat(s)
    except: 
        try: return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except: return None

def norm_type(type_key):
    if not type_key: return None
    t = type_key.lower()
    mapping = {
        "running": "running",
        "trail_running": "trail_running",
        "treadmill_running": "treadmill_running",
        "walking": "walking",
        "hiking": "hiking",
        "hiit": "hiit",
        "indoor_cardio": "hiit",
        "cross_training": "hiit",
        "strength_training": "strength_training",
        "pool_swimming": "swimming",
        "open_water_swimming": "swimming",
        "swimming": "swimming",
    }
    return mapping.get(t, t)

def pace_secs_per_km(avg_speed_mps):
    return (1000.0/avg_speed_mps) if avg_speed_mps and avg_speed_mps>0 else None

def pace_secs_per_mile(avg_speed_mps):
    return (1609.344/avg_speed_mps) if avg_speed_mps and avg_speed_mps>0 else None

def compact_splits_from_list(split_summaries):
    out = []
    if isinstance(split_summaries, list):
        for s in split_summaries:
            out.append({
                "type": s.get("splitType"),
                "n": s.get("noOfSplits"),
                "dur_s": s.get("duration"),
                "dist": s.get("distance"),
                "avg_spd": s.get("averageSpeed"),
                "ascent": s.get("totalAscent"),
            })
    return json.dumps(out, separators=(",", ":"), ensure_ascii=False) if out else None

# ---------- main ----------
def main():
    load_local_env()
    email = os.getenv("GARMIN_EMAIL")
    pwd   = os.getenv("GARMIN_PASSWORD")
    mfa   = os.getenv("GARMIN_MFA_CODE")
    g     = login(email, pwd, mfa)

    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    days = int(os.getenv("DAYS_ACTIVITIES", "30"))
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=days)
    print(
        f"Authenticated. Exporting Garmin activities from {start_date.isoformat()} to {today.isoformat()}...",
        flush=True,
    )

    # Pull list in one shot
    acts = g.get_activities_by_date(start_date.isoformat(), today.isoformat(), None) or []
    print(f"Fetched {len(acts)} activities", flush=True)

    rows = []
    total_acts = len(acts)
    for idx, a in enumerate(acts, start=1):
        # time handling
        start_local = a.get("startTimeLocal")
        dt = iso_to_dt(a.get("startTimeGMT") or start_local)
        act_date = (dt.date() if dt else None)
        activity_name = a.get("activityName") or a.get("activityId") or "activity"
        print(f"[{idx}/{total_acts}] Processing {activity_name}", flush=True)

        tkey = norm_type(a.get("activityType", {}).get("typeKey"))
        avg_spd = a.get("averageSpeed")

        base = {
            "date": act_date.isoformat() if act_date else (start_local[:10] if start_local else None),
            "activity_id": a.get("activityId"),
            "name": a.get("activityName"),
            "type_key": tkey,
            "start_local": start_local,
            "start_gmt": a.get("startTimeGMT"),
            "location": a.get("locationName"),
            "polyline": bool(a.get("hasPolyline")),

            # Core metrics from list object
            "distance_m": a.get("distance"),
            "elapsed_sec": a.get("elapsedDuration"),
            "moving_sec": a.get("movingDuration"),
            "duration_sec": a.get("duration"),
            "avg_speed_mps": avg_spd,
            "avg_pace_sec_per_km": pace_secs_per_km(avg_spd),
            "avg_pace_sec_per_mile": pace_secs_per_mile(avg_spd),
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "calories": a.get("calories"),
            "steps": a.get("steps"),
            "elev_gain_m": a.get("elevationGain"),
            "elev_loss_m": a.get("elevationLoss"),
            "training_effect": a.get("aerobicTrainingEffect"),
            "anaerobic_te": a.get("anaerobicTrainingEffect"),
            "training_load": a.get("activityTrainingLoad"),
            "vo2max": a.get("vO2MaxValue"),
            "body_battery_delta": a.get("differenceBodyBattery"),
            "intensity_min_mod": a.get("moderateIntensityMinutes"),
            "intensity_min_vig": a.get("vigorousIntensityMinutes"),
        }

        # Enrich per type from list-level fields
        extra = {}

        if tkey in ("running","trail_running","treadmill_running"):
            extra.update({
                "run_cadence_spm": a.get("averageRunningCadenceInStepsPerMinute") or a.get("maxRunningCadenceInStepsPerMinute"),
                "stride_len_cm": a.get("avgStrideLength"),   # list has cm-ish value named avgStrideLength
                "avg_power_w": a.get("avgPower"),
                "norm_power_w": a.get("normPower"),
                "vertical_osc_mm": a.get("avgVerticalOscillation"),
                "ground_contact_ms": a.get("avgGroundContactTime"),
                "vertical_ratio": a.get("avgVerticalRatio"),
                "terrain": "trail" if tkey=="trail_running" else "road/treadmill",
            })

        if tkey=="walking":
            extra.update({
                "walk_cadence_spm": a.get("averageRunningCadenceInStepsPerMinute") or a.get("maxRunningCadenceInStepsPerMinute"),
                "stride_len_cm": a.get("avgStrideLength"),
            })

        if tkey=="hiking":
            extra.update({
                "hike_cadence_spm": a.get("averageRunningCadenceInStepsPerMinute"),
                "max_elev_m": a.get("maxElevation"),
            })

        if tkey in ("hiit","strength_training","cross_training"):
            extra.update({
                "total_sets": a.get("totalSets"),
                "active_sets": a.get("activeSets"),
                "total_reps": a.get("totalReps"),
            })

        if tkey=="swimming":
            # not present in your recent data but keep placeholders
            extra.update({
                "pool_length_m": a.get("poolLength"),
                "total_lengths": a.get("totalNumberOfLengths"),
                "total_strokes": a.get("totalNumberOfStrokes"),
                "swolf_avg": a.get("avgSwolf"),
            })

        # Splits are provided inline on list items
        base["splits_json"] = compact_splits_from_list(a.get("splitSummaries"))

        rows.append({**base, **extra})

    if not rows:
        raise RuntimeError("No activities found in window — check DAYS_ACTIVITIES or Garmin sync.")

    df = pd.DataFrame(rows).sort_values(["date","start_local","activity_id"])
    out = data_dir / "latest_activity_summary.csv"
    print(f"Writing {len(df)} activity rows to {out.name}", flush=True)
    df.to_csv(out, index=False)
    print(f"✅ saved {out.name} with {len(df)} rows")
    # Also save a dated archive
    dated = data_dir / f"activities_{today.isoformat()}.csv"
    df.to_csv(dated, index=False)
    print(f"Archive write complete: {dated.name}", flush=True)
    print(f"🗃️ archived as {dated.name}")

if __name__ == "__main__":
    main()
