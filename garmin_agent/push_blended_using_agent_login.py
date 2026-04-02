from pathlib import Path
import json
import os
import sys

from auth import load_local_env, login


def main():
    load_local_env()
    here = Path(__file__).parent
    payload_path = here / "data" / "garmin_payload.json"
    if not payload_path.exists():
        print("Missing garmin_payload.json. Run blend_for_garmin.py first.", file=sys.stderr)
        sys.exit(2)

    print(f"Loading Garmin payload from {payload_path.name}", flush=True)
    p = json.load(open(payload_path))
    email = os.getenv("GARMIN_EMAIL")
    pwd = os.getenv("GARMIN_PASSWORD")
    mfa = os.environ.get("GARMIN_MFA_CODE")

    print(f"Authenticating to Garmin for body composition upload on {p['date']}", flush=True)
    g = login(email, pwd, mfa)

    print("Submitting body composition payload...", flush=True)
    resp = g.add_body_composition(
        p["date"],
        weight=p["weight"],
        percent_fat=p["percent_fat"],
        percent_hydration=p["percent_hydration"],
        visceral_fat_mass=p["visceral_fat_mass"],
        bone_mass=p["bone_mass"],
        muscle_mass=p["muscle_mass"],
        basal_met=p["basal_met"],
        active_met=p["active_met"],
        physique_rating=p["physique_rating"],
        metabolic_age=p["metabolic_age"],
        visceral_fat_rating=p["visceral_fat_rating"],
        bmi=p["bmi"],
    )
    print("Push response:", resp)
    print("Uploaded for", p["date"], flush=True)


if __name__ == "__main__":
    main()
