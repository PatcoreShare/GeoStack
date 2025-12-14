#!/usr/bin/env python3
import os, sys, subprocess, time
from pathlib import Path

VOIVODESHIPS = [
    "Dolnośląskie", "Kujawsko-pomorskie", "Lubelskie", "Lubuskie", 
    "Łódzkie", "Małopolskie", "Mazowieckie", 
    "Opolskie", "Podkarpackie", "Podlaskie", "Pomorskie", 
    "Śląskie", "Świętokrzyskie", "Warmińsko-mazurskie", "Wielkopolskie", 
    "Zachodniopomorskie"
]

def run_job():
    geojson_temp = "/app/OSM_Data/geojson_temp"
    voiv_file = f"{geojson_temp}/voivodeships.geojson"
    
    # ✅ Pobierz granice RAZ (tylko jeśli nie istnieje)
    if not os.path.exists(voiv_file):
        print("📥 Pobieram granice województw (1x)...")
        subprocess.run([
            "python", "osm_downloader.py", "-c", "config.json",
            "--region", "all", "--layers", "boundary_voivodeship"
        ], cwd="/app")
    
    for i, voivodeship in enumerate(VOIVODESHIPS, 1):
        print(f"\n{'='*60}")
        print(f"📍 [{i}/{len(VOIVODESHIPS)}] {voivodeship}")
        print(f"{'='*60}")
        
        process = subprocess.Popen([
            "python", "osm_downloader.py",
            "-c", "config.json",
            "--region", voivodeship
        ], cwd="/app", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
           text=True, bufsize=1, universal_newlines=True)
        
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
        
        rc = process.poll()
        status = "✅ OK" if rc == 0 else f"❌ BŁĄD({rc})"
        print(f"\n{status} {voivodeship}")
        
        time.sleep(5)  # Krótsza pauza

if __name__ == "__main__":
    print("🚀 === OSM Scheduler (35 warstw × 16 województw) ===")
    run_job()
