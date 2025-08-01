!pip install git+https://github.com/cyberjunky/python-garminconnect.git
from google.colab import drive
import os, json
from datetime import datetime, timedelta
import pandas as pd
from garminconnect import Garmin
from getpass import getpass

# Unmount Google Drive (if currently mounted)
try:
    drive.flush_and_unmount()
    print("Drive unmounted successfully.")
except ValueError:
    pass  # Drive might not be mounted, ignore the error

# Delete the existing folder (optional but recommended for clean setup)
!rm -rf /content/drive

# Mount Drive and set up folder
drive.mount('/content/drive')
folder_path = "/content/drive/MyDrive/Garmin Data"
os.makedirs(folder_path, exist_ok=True)