"""
garmin_to_drive.py
====================

This script logs into your Garmin Connect account, pulls the last 30 days of
health and activity data, writes each day's data to a JSON file and
generates a consolidated CSV summary.  The files are stored in a local
``data`` directory.  Optionally, if you provide Google Drive credentials
via environment variables, the script can upload the generated files to a
folder in your Drive.

Environment variables
---------------------

The script expects the following environment variables to be set when it
runs:

* ``GARMIN_EMAIL`` – your Garmin account email.
* ``GARMIN_PASSWORD`` – your Garmin account password.  **Do not hard‑code
  your password**; store it in a secret store (e.g. GitHub Secrets) and
  expose it as an environment variable.
* ``GARMIN_MFA_CODE`` – optional one‑time multi‑factor authentication code
  if your account requires it.  When MFA is required, the script will
  attempt to use this value; if it is not provided and MFA is needed, the
  script will fail.
* ``GOOGLE_SERVICE_ACCOUNT_JSON`` – **optional** JSON string for a Google
  service account with permission to write to your Drive.  If this
  variable is defined along with ``GOOGLE_DRIVE_FOLDER_ID``, the script
  will attempt to upload each generated file to the specified folder.
* ``GOOGLE_DRIVE_FOLDER_ID`` – **optional** ID of a folder in your
  Google Drive into which the files should be uploaded.  This must be
  provided alongside ``GOOGLE_SERVICE_ACCOUNT_JSON`` in order for uploads
  to occur.

Usage
-----

This script is designed to be run from a scheduled task, such as a
cron job or a GitHub Actions workflow.  For GitHub Actions, you would
store your credentials in repository secrets and expose them as
environment variables when the workflow runs.

Note that this script does not attempt to install its Python dependencies.
You should provide a ``requirements.txt`` file in the same repository
listing the following packages:

    python-garminconnect @ git+https://github.com/cyberjunky/python-garminconnect.git
    pandas
    google-api-python-client
    google-auth
    google-auth-httplib2
    google-auth-oauthlib
    google-auth

or install them via your chosen environment before running.

"""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from garminconnect import Garmin

try:
    # Google Drive dependencies are optional; import lazily
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError:
    # If the Google API libs aren't installed, uploads will be disabled
    service_account = None  # type: ignore
    build = None  # type: ignore
    MediaFileUpload = None  # type: ignore


def login_to_garmin(email: str, password: str, mfa: Optional[str] = None) -> Garmin:
    """Log into Garmin and return a client instance.

    Attempts to use a cached token store in the current directory
    (``.garminconnect``).  If that fails, performs a full login using
    the provided credentials.  If your account requires MFA, provide
    ``mfa``; if omitted and MFA is required, the login will fail.

    Args:
        email: Garmin account email address.
        password: Garmin account password.
        mfa: Optional one‑time MFA code.

    Returns:
        An authenticated ``Garmin`` client.
    """
    tokenstore = Path(".garminconnect")
    client = Garmin()
    try:
        # Attempt to reuse an existing session
        client.login(str(tokenstore))
        print("✅ Logged in using saved token.")
    except Exception:
        print("ℹ️  Saved token not found or invalid; performing full login…")
        client = Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)
        result1, result2 = client.login()
        if result1 == "needs_mfa":
            if not mfa:
                raise RuntimeError(
                    "This Garmin account requires MFA; set the GARMIN_MFA_CODE environment variable."
                )
            client.resume_login(result2, mfa)
        # Persist the session so future runs won't require MFA
        client.garth.dump(str(tokenstore))
        print("✅ Logged in and saved token.")
    return client


def fetch_daily_data(client: Garmin, target_date: date) -> Dict[str, object]:
    """Fetch all of the relevant Garmin data for a single date.

    This function calls a number of Garmin Connect API endpoints and
    collects the results into a dictionary.  If any call fails, the
    exception is caught and logged; the corresponding key will be
    missing from the dictionary.

    Args:
        client: Authenticated Garmin client.
        target_date: The date for which to fetch data.

    Returns:
        A dictionary of data keyed by API name.
    """
    date_str = target_date.isoformat()
    daily_data: Dict[str, object] = {}
    try:
        daily_data["activity_stats"] = client.get_stats(date_str)
        daily_data["body_composition"] = client.get_body_composition(date_str)
        daily_data["steps"] = client.get_steps_data(date_str)
        daily_data["heart_rate"] = client.get_heart_rates(date_str)
        daily_data["training_readiness"] = client.get_training_readiness(date_str)
        daily_data["body_battery"] = client.get_body_battery(date_str, date_str)
        daily_data["training_status"] = client.get_training_status(date_str)
        daily_data["resting_hr"] = client.get_rhr_day(date_str)
        daily_data["sleep"] = client.get_sleep_data(date_str)
        daily_data["stress"] = client.get_stress_data(date_str)
        daily_data["respiration"] = client.get_respiration_data(date_str)
        daily_data["spo2"] = client.get_spo2_data(date_str)
        daily_data["max_metrics"] = client.get_max_metrics(date_str)
        daily_data["hrv"] = client.get_hrv_data(date_str)
        daily_data["hill_score"] = client.get_hill_score(date_str, date_str)
        daily_data["endurance_score"] = client.get_endurance_score(date_str, date_str)
        daily_data["race_predictions"] = client.get_race_predictions()
        daily_data["all_day_stress"] = client.get_all_day_stress(date_str)
        daily_data["fitness_age"] = client.get_fitnessage_data(date_str)
    except Exception as e:
        # Catch generic exceptions so one failing endpoint won't abort the run
        print(f"⚠️  Error pulling data for {date_str}: {e}")
    return daily_data


def save_json(data: Dict[str, object], path: Path) -> None:
    """Save a dictionary to a JSON file with pretty formatting."""
    with path.open("w") as f:
        json.dump(data, f, indent=4)


def build_summary(records: List[Dict[str, object]]) -> pd.DataFrame:
    """Construct a pandas DataFrame summarising the collected data.

    This function mirrors the summary logic from the original Colab script,
    extracting fields from the nested JSON structures and flattening them
    into a tabular format.

    Args:
        records: A list of dictionaries, each representing a day of
            collected Garmin data.  The caller is responsible for
            providing the date associated with each record via the
            ``"date"`` key.

    Returns:
        A ``pandas.DataFrame`` sorted by date.
    """
    flattened: List[Dict[str, object]] = []
    for entry in records:
        date_str = entry.get("date")
        data = entry.get("data", {})

        def get(path: List[str], default=None):
            try:
                ref = data
                for p in path:
                    if isinstance(ref, list):
                        ref = ref[0]
                    ref = ref[p]
                return ref
            except Exception:
                return default

        record: Dict[str, object] = {
            "date": date_str,
            "readiness": get(["training_readiness", "score"]),
            "hrv": get(["hrv", "hrvSummary", "lastNightAvg"]),
            "rhr": get(["heart_rate", "restingHeartRate"]),
            "sleep_hrs": round((get(["sleep", "dailySleepDTO", "sleepTimeSeconds"], 0) or 0) / 3600, 2),
            "steps": get(["activity_stats", "totalSteps"]),
            "stress_avg": get(["activity_stats", "averageStressLevel"]),
            "stress_dur": round((get(["activity_stats", "stressDuration"], 0) or 0) / 3600, 2),
            "calories_active": get(["activity_stats", "activeKilocalories"]),
            "bb_start": get(["activity_stats", "bodyBatteryAtWakeTime"]),
            "bb_end": get(["activity_stats", "bodyBatteryMostRecentValue"]),
            "bb_low": get(["activity_stats", "bodyBatteryLowestValue"]),
            "vo2max": get(["training_status", "mostRecentVO2Max", "generic", "vo2MaxValue"]),
            "fitness_age": round((get(["fitness_age", "fitnessAge"], 0) or 0), 2),
            "respiration_avg": get(["sleep", "dailySleepDTO", "averageRespirationValue"]),
            "acute_training_load": get([
                "training_status",
                "mostRecentTrainingStatus",
                "latestTrainingStatusData",
                "3449644769",
                "acuteTrainingLoadDTO",
                "acwrStatus",
            ]),
            "training_need": get([
                "training_status",
                "mostRecentTrainingLoadBalance",
                "metricsTrainingLoadBalanceDTOMap",
                "3449644769",
                "trainingBalanceFeedbackPhrase",
            ]),
        }

        # Activities summary
        try:
            activity_events = data.get("activity_stats", {}).get("bodyBatteryActivityEventList", [])
            activity_pairs = []
            for a in activity_events:
                if a.get("eventType") == "ACTIVITY":
                    name = a.get("activityType", "unknown").lower()
                    feedback = a.get("shortFeedback", "none").upper()
                    activity_pairs.append(f"{name}-{feedback}")
            record["activities"] = ", ".join(activity_pairs)
        except Exception:
            record["activities"] = ""

        # Body composition metrics
        try:
            comp = data.get("body_composition", {}).get("totalAverage", {})
            record["weight"] = round(comp.get("weight", 0) / 1000, 2) if comp.get("weight") else None
            record["percent_fat"] = comp.get("bodyFat")
            record["muscle_mass"] = round(comp.get("muscleMass", 0) / 1000, 2) if comp.get("muscleMass") else None
            record["bone_mass"] = round(comp.get("boneMass", 0) / 1000, 2) if comp.get("boneMass") else None
            record["bmi"] = round(comp.get("bmi", 0), 2) if comp.get("bmi") else None
            record["visceral_fat"] = comp.get("visceralFat")

            # Metabolic age (convert from ms since epoch if present)
            raw_meta_age = comp.get("metabolicAge")
            if isinstance(raw_meta_age, (int, float)) and raw_meta_age > 1e12:
                meta_age_dt = datetime.fromtimestamp(raw_meta_age / 1000.0)
                record["metabolic_age"] = date.fromtimestamp(meta_age_dt.timestamp()).year - meta_age_dt.year
            else:
                record["metabolic_age"] = None
        except Exception:
            record.update({
                "weight": None,
                "percent_fat": None,
                "muscle_mass": None,
                "bone_mass": None,
                "bmi": None,
                "visceral_fat": None,
                "metabolic_age": None,
            })

        flattened.append(record)

    return pd.DataFrame(flattened).sort_values("date")


def upload_to_drive(folder: Path, drive_folder_id: str, service_account_info: Dict[str, object]) -> None:
    """Upload all files in ``folder`` to a Google Drive folder.

    This helper uses a service account specified by ``service_account_info``
    to authenticate with the Drive API.  Each file is uploaded with its
    filename preserved.  If a file with the same name already exists in the
    target folder, this code will create a duplicate; overwriting is not
    handled.

    Args:
        folder: Path to the local folder containing files to upload.
        drive_folder_id: ID of the destination folder in Google Drive.
        service_account_info: Parsed JSON credentials for a Google service
            account.  You can generate this via the Google Cloud console.
    """
    if service_account is None or build is None or MediaFileUpload is None:
        raise RuntimeError(
            "Google API libraries are not installed; cannot upload to Drive."
        )
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    drive_service = build("drive", "v3", credentials=creds)
    for file_path in folder.iterdir():
        if not file_path.is_file():
            continue
        file_metadata = {"name": file_path.name, "parents": [drive_folder_id]}
        media = MediaFileUpload(str(file_path), resumable=True)
        request = drive_service.files().create(body=file_metadata, media_body=media, fields="id")
        response = None
        while response is None:
            status, response = request.next_chunk()  # type: ignore
            if status:
                print(f"Uploading {file_path.name}: {int(status.progress() * 100)}%")
        print(f"✅ Uploaded {file_path.name} to Google Drive")


def main() -> None:
    """Entry point for running the data collection and upload.

    This function ties together authentication, data retrieval, file
    writing, summary generation and optional upload to Google Drive.  It
    calculates the last 30 days of dates relative to today and iterates
    through them.  On each iteration it fetches data, saves it to
    ``data/<YYYY-MM-DD>.json`` and appends a record for summary.  After
    processing all dates it writes a CSV summary file named
    ``garmin_summary_<YYYY-MM-DD>.csv`` into the ``data`` folder.

    Upload to Drive is attempted only if both ``GOOGLE_SERVICE_ACCOUNT_JSON``
    and ``GOOGLE_DRIVE_FOLDER_ID`` environment variables are defined.
    """
    # Read credentials from environment
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    mfa = os.environ.get("GARMIN_MFA_CODE")
    if not email or not password:
        raise RuntimeError(
            "GARMIN_EMAIL and GARMIN_PASSWORD environment variables must be set."
        )

    # Prepare local data directory
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)

    # Authenticate with Garmin
    client = login_to_garmin(email, password, mfa)

    # Collect data for the last 30 days
    today = date.today()
    days_back = 30
    records: List[Dict[str, object]] = []
    for i in range(days_back):
        dt = today - timedelta(days=i)
        date_str = dt.isoformat()
        print(f"📅 Pulling data for {date_str}…")
        data = fetch_daily_data(client, dt)
        # Save each day's raw JSON
        json_path = data_dir / f"{date_str}.json"
        save_json(data, json_path)
        print(f"✅ Data for {date_str} saved to {json_path}")
        records.append({"date": date_str, "data": data})

    # Build and save the summary CSV
    df = build_summary(records)
    summary_path = data_dir / f"garmin_summary_{today.isoformat()}.csv"
    df.to_csv(summary_path, index=False)
    print(f"✅ Summary saved to {summary_path}")

    # Optional upload to Google Drive
    service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    drive_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if service_account_json and drive_folder_id:
        try:
            service_account_info = json.loads(service_account_json)
            upload_to_drive(data_dir, drive_folder_id, service_account_info)
        except Exception as e:
            print(f"⚠️  Google Drive upload failed: {e}")
    else:
        print(
            "ℹ️  GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_DRIVE_FOLDER_ID not set; skipping Drive upload."
        )


if __name__ == "__main__":
    main()