from pathlib import Path
from datetime import date
import json, os, sys

def lbs_to_kg(lbs: float) -> float:
    return round(float(lbs) * 0.453592, 2)

def blend(std: float, ath: float, w_std: float, w_ath: float) -> float:
    return round((w_std * float(std)) + (w_ath * float(ath)), 2)

def need(d: dict, k: str):
    if k not in d:
        raise KeyError(f"Missing key: {k}")
    return d[k]

def main():
    here = Path(__file__).parent
    data_dir = here / "data"
    ath = json.load(open(data_dir / "tj_ath.json"))
    std = json.load(open(data_dir / "tj_standard.json"))

    w_std = float(os.getenv("WEIGHT_STD", "0.6"))
    w_ath = float(os.getenv("WEIGHT_ATH", "0.4"))
    if abs((w_std + w_ath) - 1.0) > 1e-6:
        print("ERROR: WEIGHT_STD + WEIGHT_ATH must equal 1.0", file=sys.stderr)
        sys.exit(2)

    weight_lbs = need(std, "weight_lb")
    muscle_ath = need(ath, "muscle_mass_lb")
    skeletal_pct_ath = need(ath, "skeletal_muscle_percent")
    bone_ath = need(ath, "bone_mass_lb")
    vis_fat_ath = need(ath, "visceral_fat")
    fat_pct_ath = need(ath, "body_fat_percent")
    hydration_ath = need(ath, "body_water_percent")
    bmi_ath = need(ath, "bmi")
    bmr_ath = need(ath, "bmr_kcal")
    meta_age_ath = need(ath, "metabolic_age")

    muscle_std = need(std, "muscle_mass_lb")
    skeletal_pct_std = need(std, "skeletal_muscle_percent")
    bone_std = need(std, "bone_mass_lb")
    vis_fat_std = need(std, "visceral_fat")
    fat_pct_std = need(std, "body_fat_percent")
    hydration_std = need(std, "body_water_percent")
    bmi_std = need(std, "bmi")
    bmr_std = need(std, "bmr_kcal")
    meta_age_std = need(std, "metabolic_age")

    weight_kg = lbs_to_kg(weight_lbs)
    muscle_mass_kg = lbs_to_kg(blend(muscle_std, muscle_ath, w_std, w_ath))
    skeletal_pct = blend(skeletal_pct_std, skeletal_pct_ath, w_std, w_ath)
    skeletal_mass_kg = round(weight_kg * (skeletal_pct / 100.0), 2)
    bone_mass_kg = lbs_to_kg(blend(bone_std, bone_ath, w_std, w_ath))
    visceral_fat_rating = blend(vis_fat_std, vis_fat_ath, w_std, w_ath)
    percent_fat = blend(fat_pct_std, fat_pct_ath, w_std, w_ath)
    percent_hydration = blend(hydration_std, hydration_ath, w_std, w_ath)
    bmi = blend(bmi_std, bmi_ath, w_std, w_ath)
    basal_met = blend(bmr_std, bmr_ath, w_std, w_ath)
    metabolic_age = blend(meta_age_std, meta_age_ath, w_std, w_ath)

    payload = {
        "date": date.today().isoformat(),
        "weight": weight_kg,
        "percent_fat": percent_fat,
        "percent_hydration": percent_hydration,
        "visceral_fat_mass": visceral_fat_rating,
        "bone_mass": bone_mass_kg,
        "muscle_mass": skeletal_mass_kg,  # skeletal mass
        "basal_met": basal_met,
        "active_met": None,
        "physique_rating": None,
        "metabolic_age": metabolic_age,
        "visceral_fat_rating": visceral_fat_rating,
        "bmi": bmi,
        "_debug": {"skeletal_pct": skeletal_pct, "muscle_mass_total_kg": muscle_mass_kg},
    }

    out = data_dir / "garmin_payload.json"
    json.dump(payload, open(out, "w"), indent=2)
    print(out.read_text())

if __name__ == "__main__":
    main()
