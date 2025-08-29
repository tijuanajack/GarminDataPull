from pathlib import Path
import json, os, sys

# ensure we can import garmin_to_drive.py sitting next to this file
here = Path(__file__).parent
sys.path.insert(0, str(here))

from garmin_to_drive import login

def main():
    payload_path = here / "data" / "garmin_payload.json"
    if not payload_path.exists():
        print("Missing garmin_payload.json. Run blend_for_garmin.py first.", file=sys.stderr)
        sys.exit(2)

    p = json.load(open(payload_path))
    email = os.environ["GARMIN_EMAIL"]
    pwd   = os.environ["GARMIN_PASSWORD"]
    mfa   = os.environ.get("GARMIN_MFA_CODE")

    g = login(email, pwd, mfa)

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
    print("Uploaded for", p["date"])

if __name__ == "__main__":
    main()
