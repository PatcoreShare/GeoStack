#!/usr/bin/env python3
"""
GeoTiles (OSM) Scheduler - automatyczne pobieranie dla wszystkich województw.
Nazwa pliku: województwo-geotiles_zMIN-MAX_timestamp.mbtiles
"""

import os
import time
import subprocess
import json
from datetime import datetime

INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", "86400"))
CONFIG_PATH = os.getenv("CONFIG_PATH", "/app/config.json")
MIN_ZOOM = os.getenv("MIN_ZOOM", "10")
MAX_ZOOM = os.getenv("MAX_ZOOM", "11")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/app/data")

def load_regions():
    """Wczytuje województwa z config.json."""
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)['tiles_settings']
        return config.get('regions', {})
    except Exception as e:
        print(f"❌ Błąd wczytywania config.json: {e}")
        return {}

def run_job():
    """Pobiera mapy dla wszystkich województw."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    regions = load_regions()
    if not regions:
        print("❌ Brak województw w config.json - używam domyślnych bbox")
        ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
        output_path = f"{OUTPUT_DIR}/geotiles_osm_z{MIN_ZOOM}-{MAX_ZOOM}_{ts}.mbtiles"
        
        cmd = [
            "python", "main.py",
            "-b", os.getenv("BBOX_W", "14.0"), os.getenv("BBOX_S", "48.5"), 
                 os.getenv("BBOX_E", "24.5"), os.getenv("BBOX_N", "55.0"),
            "--min-zoom", MIN_ZOOM,
            "--max-zoom", MAX_ZOOM,
            "--output", output_path
        ]
        
        print("=== GeoTiles (OSM) Scheduler (DOMYŚLNY) ===")
        print("Output:", output_path)
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(f"Job finished: {result.returncode}")
        return
    
    # Pobieranie dla każdego województwa
    print("=== GeoTiles (OSM) Scheduler - WSZYSTKIE WOJEWÓDZTWA ===")
    success_count = 0
    
    for region_id, region_data in regions.items():
        ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
        # NAZWA: województwo-geotiles_zMIN-MAX_timestamp.mbtiles
        region_name = region_data['name'].lower().replace(' ', '-').replace('ł', 'l').replace('ą', 'a')
        output_path = f"{OUTPUT_DIR}/{region_name}-geotiles_z{MIN_ZOOM}-{MAX_ZOOM}_{ts}.mbtiles"
        
        bbox = region_data['bbox']
        cmd = [
            "python", "main.py",
            "-b", str(bbox['west']), str(bbox['south']), 
                 str(bbox['east']), str(bbox['north']),
            "--min-zoom", MIN_ZOOM,
            "--max-zoom", MAX_ZOOM,
            "--output", output_path
        ]
        
        print(f"\n📍 {region_data['name']} (ID: {region_id})")
        print(f"📄 Plik: {os.path.basename(output_path)}")
        print("Running:", " ".join(cmd))
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(f"Return code: {result.returncode}")
        
        if result.returncode == 0:
            print(f"✅ {region_data['name']} - SUKCES")
            success_count += 1
        else:
            print(f"❌ {region_data['name']} - BŁĄD")
            print(result.stderr[:300])
        
        time.sleep(3)  # Przerwa między województwami
    
    print(f"\n📊 PODSUMOWANIE: {success_count}/{len(regions)} województw OK")

def main():
    while True:
        run_job()
        print(f"Sleeping for {INTERVAL_SECONDS} seconds ({INTERVAL_SECONDS/3600:.1f}h)...")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
