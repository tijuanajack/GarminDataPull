# garmin_agent/dump_raw_activities.py
from garminconnect import Garmin
from pathlib import Path
from datetime import datetime, timedelta, timezone
import os, json

# helpers
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

    # 1) list
    try:
        acts = g.get_activities_by_date(start_date.isoformat(), today.isoformat(), None) or []
    except Exception:
        # fallback to pagination
        acts = []
        page = 0; size = 200
        while True:
            batch = g.get_activities(page, size) or []
            if not batch: break
            acts += batch
            page += size
            # stop if the last item is older than window
            last = batch[-1]
            start_gmt = last.get("startTimeGMT")
            if start_gmt:
                # simple date check without parsing
                if str(start_date) > start_gmt[:10]:
                    break

    list_path = data_dir / "activities_list.json"
    with open(list_path, "w", encoding="utf-8") as f:
        json.dump(acts, f, ensure_ascii=False, indent=2)
    print(f"wrote {list_path} with {len(acts)} items")

    # 2) details for each activity
    details_path = data_dir / "activities_details.jsonl"
    written = 0
    with open(details_path, "w", encoding="utf-8") as out:
        for a in acts:
            act_id = a.get("activityId")
            if not act_id:
                continue
            try:
                det = g.get_activity_details(act_id) or {}
            except Exception as e:
                det = {"error": str(e), "activityId": act_id}
            # include a few top-level fields from list for context
            det["_list"] = {
                "activityId": act_id,
                "activityName": a.get("activityName"),
                "activityType": a.get("activityType"),
                "startTimeLocal": a.get("startTimeLocal"),
                "startTimeGMT": a.get("startTimeGMT"),
                "summaryDTO": a.get("summaryDTO"),
            }
            out.write(json.dumps(det, ensure_ascii=False) + "\n")
            written += 1
    print(f"wrote {details_path} with {written} lines")

if __name__ == "__main__":
    main()
