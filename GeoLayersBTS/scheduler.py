#!/usr/bin/env python3
"""
BTS Downloader Scheduler - styl GeoSatellite.
"""

import os
import time
import subprocess
from datetime import datetime

# Konfiguracja z env vars (domyślne wartości)
INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", "21600"))  # 6h domyślnie
CONFIG_PATH = os.getenv("CONFIG_PATH", "/app/config.json")
DATE_SUFFIX = os.getenv("DATE_SUFFIX", "auto")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/app/KMZ")

def run_job():
    """Uruchamia bts_downloader.py z parametrami."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Znacznik czasu rrrr-mm-dd-hh-mm (tylko jeśli DATE_SUFFIX=auto)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M") if DATE_SUFFIX == "auto" else DATE_SUFFIX
    
    cmd = [
        "python", "bts_downloader.py",
        "-c", CONFIG_PATH
    ]
    
    if DATE_SUFFIX != "auto":
        cmd.extend(["--date-suffix", DATE_SUFFIX])

    print("=== BTS Downloader Scheduler ===")
    print("Running job with:")
    print(" ", " ".join(cmd))
    print(f"Output dir: {OUTPUT_DIR}")
    print(f"Config: {CONFIG_PATH}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"Job finished with return code: {result.returncode}")
    
    if result.returncode == 0:
        print("✅ Job success!")
        print(result.stdout)
    else:
        print("❌ Job failed!")
        print(result.stderr)

def main():
    while True:
        run_job()
        print(f"Sleeping for {INTERVAL_SECONDS} seconds ({INTERVAL_SECONDS/3600:.1f}h)...")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
