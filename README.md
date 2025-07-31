# Garmin Data Sync Agent

This repository contains a lightweight automation for retrieving your
Garmin Connect data and backing it up to a Google Drive folder on a daily
basis.  It is intended to be run from a GitHub Actions workflow, which
means you don't need to keep your own machine running to collect the
data—GitHub will execute the workflow on their hosted runners for
free.

## How it works

1. The core logic lives in [`garmin_to_drive.py`](garmin_to_drive.py).  When
   executed, it logs into your Garmin Connect account (using
   credentials you supply via environment variables), fetches the last
   30 days of data from a variety of Garmin APIs, stores each day's
   results as a JSON file under the `data` directory and then creates a
   summary CSV file that aggregates key metrics.
2. If you additionally provide a Google Drive service‑account JSON and
   folder ID via environment variables, the script will upload the
   generated files to your Drive.  These steps are optional; if no
   Drive credentials are provided the files remain in the `data`
   directory within the repository workspace.
3. The GitHub Actions workflow defined in
   [`.github/workflows/daily.yml`](.github/workflows/daily.yml) checks
   out your repository on a fresh runner, installs the required
   dependencies, exports your secrets as environment variables and runs
   the script.  By default the workflow is scheduled to run every day
   at 09:00 UTC (03:00 America/Chicago) and can also be triggered
   manually.

## Setup instructions

1. **Create a new GitHub repository** and populate it with the
   contents of this directory (`garmin_agent`).  You can either commit
   the files manually or fork this repo.
2. **Add the following secrets** in your repository settings (under
   *Settings → Secrets and variables → Actions → New repository secret*):

   | Secret name                  | Description                                             |
   |------------------------------|---------------------------------------------------------|
   | `GARMIN_EMAIL`               | Your Garmin account email address.                     |
   | `GARMIN_PASSWORD`            | Your Garmin account password.                          |
   | `GARMIN_MFA_CODE`            | (Optional) An MFA code if your account requires it.    |
   | `GOOGLE_SERVICE_ACCOUNT_JSON` | (Optional) JSON for a Google service account.          |
   | `GOOGLE_DRIVE_FOLDER_ID`     | (Optional) ID of the Drive folder to upload files into. |

   The Garmin email and password are required.  If you do not wish to
   upload to Google Drive, you can omit the Drive‑related secrets and
   the script will simply write the data to the repository workspace.
3. **Adjust the schedule** if necessary by editing the `cron` value in
   `.github/workflows/daily.yml`.  The current setting runs daily at
   09:00 UTC.  You can consult [crontab.guru](https://crontab.guru/) to
   convert this to your preferred time.
4. **Push your changes** to GitHub.  The first run of the workflow will
   occur at the next scheduled time, or you can trigger it manually
   from the *Actions* tab.

## Notes

* This automation uses the unofficial [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect)
  library.  Garmin may change their APIs at any time; if a call fails
  the script will log the error but continue pulling other data.
* The Google Drive upload uses a service account.  See the official
  [Google Drive API documentation](https://developers.google.com/drive)
  for instructions on creating a service account and enabling the
  Drive API.  After creating a service account, generate a JSON key
  and paste its contents into the `GOOGLE_SERVICE_ACCOUNT_JSON` secret.
