#!/usr/bin/env python3
"""
BTS Downloader - Pobiera dane stacji bazowych z BTSearch.pl do KMZ.
Poprawiona wersja z wykrywaniem operatorów i kolorami.
"""

import requests
import re
import os
import simplekml
import time
import json
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Poprawione mapowanie sieci (bez NetWorkS!)
NETWORKS = {
    "26001": "Plus", "26002": "T-Mobile", "26003": "Orange", "26006": "Play",
    "26010": "Sferia", "26011": "Nordisk", "26015": "Centernet", "26016": "Mobyland",
    "26017": "Aero2", "26018": "PGE Systemy"
}

REGIONS = {
    "1": "Dolnośląskie", "2": "Kujawsko-pomorskie", "3": "Lubelskie", "4": "Lubuskie",
    "5": "Łódzkie", "6": "Małopolskie", "7": "Mazowieckie", "8": "Opolskie",
    "9": "Podkarpackie", "10": "Podlaskie", "11": "Pomorskie", "12": "Śląskie",
    "13": "Świętokrzyskie", "14": "Warmińsko-mazurskie", "15": "Wielkopolskie",
    "16": "Zachodniopomorskie"
}

def setup_logging(log_dir):
    """Logi tylko do pliku."""
    os.makedirs(log_dir, exist_ok=True)
    log_file = f"{log_dir}/bts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)
    
    print(f"📝 Logi: {log_file}")
    return logger

def parse_args():
    parser = argparse.ArgumentParser(description="Pobiera BTS do KMZ")
    parser.add_argument('-c', '--config', required=True, help='config.json')
    parser.add_argument('--date-suffix', help='Sufiks daty dla plików')
    return parser.parse_args()

def load_config(config_file):
    with open(config_file) as f:
        return json.load(f)['bts_settings']

def get_csrf(session, export_url):
    """Pobiera CSRF token."""
    r = session.get(export_url)
    csrf = re.search(r"name='csrfmiddlewaretoken' value='([^']+)'", r.text).group(1)
    return csrf

def extract_operators_from_description(desc, major_operators):
    """Wykrywa operatorów z opisu stacji (z starego kodu)."""
    found_operators = set()
    if not desc:
        return found_operators
    
    desc_upper = desc.upper()
    
    # Plus (BTxxxxx)
    if re.search(r'DLNB|T', desc, re.IGNORECASE):
        found_operators.add("Plus")
    
    # T-Mobile (różne wzorce DLN)
    tmobile_patterns = [r'DLNT-', r'DLN4,553500', r'DLN4,5G900', r'DLN4,5U900', 
                       r'DLN4,53U900', r'DLN4,5L1800', r'DLN4,5L2100', r'DLN4,5L800', r'DLN4,5L2600']
    for pattern in tmobile_patterns:
        if re.search(pattern, desc, re.IGNORECASE):
            found_operators.add("T-Mobile")
            break
    if any(p in desc_upper for p in ["WIEŻA T-MOBILE", "T-MOBILE ID"]):
        found_operators.add("T-Mobile")
    
    # Orange (kody miast + inne)
    orange_city_codes = ["WRO", "WAW", "KRK", "POZ", "GDA", "LOD", "KAT", "SZC", "BYD", "LUB"]
    for citycode in orange_city_codes:
        if re.search(rf'DLN{citycode}', desc, re.IGNORECASE):
            found_operators.add("Orange")
            break
    if re.search(r'DLNO-', desc, re.IGNORECASE) or any(p in desc_upper for p in ["WIEŻA ORANGE", "ORANGE ID"]):
        found_operators.add("Orange")
    
    # Play (NWA-Z + inne)
    if re.search(r'DLNN[WA-Z]{1,2}', desc, re.IGNORECASE) or any(p in desc_upper for p in ["CELLNEX PLAY", "WIEŻA PLAY"]):
        found_operators.add("Play")
    
    # Własna wieża -> Plus jako domyślny
    if "WŁASNA WIEŻA" in desc_upper and not any(op in found_operators for op in major_operators):
        found_operators.add("Plus")
    
    return found_operators

def fetch_region(session, csrf, region_id, region_name, config):
    """Pobiera dane województwa."""
    cache_file = f"{config['directories']['cache']}/{region_name.replace(' ', '_')}.clf"
    
    if os.path.exists(cache_file):
        print(f"  ✓ Cache: {region_name}")
        with open(cache_file, "rb") as f:
            return f.read()
    
    payload = {
        "csrfmiddlewaretoken": csrf,
        "network": list(NETWORKS.keys()),
        "region": region_id,
        "output_format": config['output_format']
    }
    
    try:
        r = session.post(config['export_url'], data=payload, timeout=config['timeout'])
        if r.status_code == 200 and "attachment" in r.headers.get("Content-Disposition", ""):
            content = r.content
            with open(cache_file, "wb") as f:
                f.write(content)
            print(f"  ✓ Pobrano {region_name}: {len(content)/1024:.1f}KB")
            return content
    except Exception as e:
        print(f"  ✗ Błąd {region_name}: {e}")
    
    return None

def save_kmz(region_name, clf_content, config, date_suffix=None):
    """Tworzy KMZ z kolorami i wykrywaniem operatorów."""
    if not clf_content:
        return
    
    kml = simplekml.Kml()
    lines = clf_content.decode('utf-8').splitlines()
    operator_locations = {}
    
    for line in lines:
        if not line.strip() or line.startswith('//'):
            continue
        
        parts = line.split(';')
        if len(parts) < 6:
            continue
        
        try:
            net_id, cid, lac, _, lat, lon = parts[:6]
            lat, lon = float(lat), float(lon)
            
            if not (49 <= lat <= 55 and 14 <= lon <= 24.5):
                continue
            
            # Wykrywanie operatora z NETWORKS lub opisu
            base_operator = NETWORKS.get(net_id, net_id)
            detected_operators = extract_operators_from_description(
                parts[7] if len(parts) > 7 else "", config['major_operators']
            )
            
            # Priorytet: wykryci z opisu, fallback do NETWORKS
            operators_to_use = detected_operators or {base_operator}
            
            lat_rnd, lon_rnd = round(lat, 6), round(lon, 6)
            for operator in operators_to_use:
                if operator in config['operator_colors']:  # Tylko z kolorami
                    key = f"{lat_rnd},{lon_rnd},{operator}"
                    if key not in operator_locations:
                        operator_locations[key] = {'lat': lat, 'lon': lon, 'operator': operator, 'count': 0}
                    operator_locations[key]['count'] += 1
                    
        except:
            continue
    
    # Tworzenie punktów z kolorami
    for loc in operator_locations.values():
        pnt = kml.newpoint(name=loc['operator'], coords=[(loc['lon'], loc['lat'])])
        pnt.style.iconstyle.color = config['operator_colors'][loc['operator']]
        pnt.style.iconstyle.scale = 1.2
        pnt.description = f"Operator: {loc['operator']}\nStacje: {loc['count']}"
    
    # Zapis KMZ
    kmz_dir = config['directories']['kmz']
    os.makedirs(kmz_dir, exist_ok=True)
    
    region_safe = region_name.replace(' ', '_').replace('/', '_')
    if date_suffix:
        filename = f"KMZ_BTS_{region_safe}_{date_suffix}.kmz"
    else:
        filename = f"KMZ_BTS_{region_safe}_{datetime.now().strftime('%Y-%m-%d-%H-%M')}.kmz"
    
    kmz_path = f"{kmz_dir}/{filename}"
    kml.savekmz(kmz_path)
    print(f"  ✅ Zapisano: {filename} ({len(operator_locations)} punktów)")

def main():
    args = parse_args()
    config = load_config(args.config)
    logger = setup_logging(config['directories']['logs'])
    
    print("=== BTS Downloader v2 (z kolorami i wykrywaniem operatorów) ===")
    logger.info("🚀 Rozpoczynam pobieranie BTS dla wszystkich województw")
    
    # Katalogi
    for dir_name in config['directories'].values():
        os.makedirs(dir_name, exist_ok=True)
    
    # Sesja + CSRF
    session = requests.Session()
    csrf = get_csrf(session, config['export_url'])
    
    # Pobieranie wszystkich województw
    date_suffix = args.date_suffix or datetime.now().strftime('%Y%m%d_%H%M')
    
    for region_id, region_name in REGIONS.items():
        print(f"\n📍 {region_name} (ID: {region_id})")
        clf_content = fetch_region(session, csrf, region_id, region_name, config)
        save_kmz(region_name, clf_content, config, date_suffix)
        time.sleep(config['sleep_between'])
    
    print("\n✅ GOTOWE! Sprawdź KMZ/")

if __name__ == "__main__":
    main()
