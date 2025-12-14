#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OSM Downloader - precyzyjne pobieranie danych z OpenStreetMap wg granic województw
Obsługuje pliki JSON z definicjami warstw + konwersja do KMZ
Pobiera i zapisuje lokalny GeoJSON z granicami POLSKICH województw
Używa dokładnych kształtów województw zamiast prostokątnych bbox
"""

import os
import sys
import json
import time
import math
import random
import warnings
import logging
import argparse
import pandas as pd
import geopandas as gpd
import osmnx as ox
import simplekml
from datetime import datetime
from pathlib import Path
from shapely.geometry import box

warnings.filterwarnings('ignore', category=RuntimeWarning, module='pyogrio')
osmnx_logger = logging.getLogger('osmnx')

# ============================================================================
# KONFIGURACJA
# ============================================================================

def load_config(config_file):
    """Wczytuje konfigurację z pliku JSON."""
    try:
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Nie znaleziono pliku: {config_file}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if 'osm_settings' not in config:
            raise ValueError("Brak sekcji 'osm_settings' w pliku konfiguracyjnym")
        
        return config['osm_settings']
        
    except Exception as e:
        print(f"❌ Błąd wczytywania konfiguracji: {e}")
        sys.exit(1)

def load_layers_from_file(layer_file):
    """Wczytuje definicje warstw z zewnętrznego pliku JSON."""
    try:
        if not os.path.exists(layer_file):
            raise FileNotFoundError(f"Nie znaleziono pliku warstw: {layer_file}")
        
        with open(layer_file, 'r', encoding='utf-8') as f:
            layer_data = json.load(f)
        
        if 'layers' not in layer_data:
            raise ValueError(f"Plik {layer_file} nie zawiera sekcji 'layers'")
        
        return layer_data['layers']
        
    except Exception as e:
        print(f"❌ Błąd wczytywania warstw z {layer_file}: {e}")
        return {}

def discover_layer_files(config):
    """Automatycznie skanuje katalog layers/ i wczytuje wszystkie pliki JSON."""
    import glob
    
    directories = config.get('directories', {})
    layers_dir = directories.get('layers', 'layers')
    
    all_layers = {}
    
    if not os.path.exists(layers_dir):
        print(f"⚠️ Katalog {layers_dir} nie istnieje. Tworzę...")
        os.makedirs(layers_dir, exist_ok=True)
        return all_layers
    
    json_files = glob.glob(os.path.join(layers_dir, "*.json"))
    
    if not json_files:
        print(f"⚠️ Brak plików JSON w katalogu {layers_dir}")
        return all_layers
    
    print(f"📂 Skanowanie katalogu: {layers_dir}")
    print(f"🔍 Znaleziono {len(json_files)} plików JSON\n")
    
    for filepath in sorted(json_files):
        filename = os.path.basename(filepath)
        try:
            layers = load_layers_from_file(filepath)
            if layers:
                all_layers.update(layers)
                print(f"✅ Załadowano {len(layers)} warstw z {filename}")
            else:
                print(f"⚠️ Plik {filename} nie zawiera warstw")
        except Exception as e:
            print(f"❌ Błąd wczytywania {filename}: {e}")
    
    print(f"\n📊 Łącznie załadowano {len(all_layers)} warstw")
    return all_layers

# ============================================================================
# FUNKCJE GRANIC WOJEWÓDZTW
# ============================================================================

def fetch_save_voivodeships_geojson(filepath, layers_dict, poland_bbox, config):
    """Pobiera i zapisuje granice POLSKICH województw z OSM z kafelkowaniem i postępem."""
    if os.path.exists(filepath):
        print(f"✔️  Plik granic województw istnieje: {filepath}")
        return

    layer = layers_dict.get("boundary_voivodeship")
    if not layer:
        print("⚠️ Brak definicji warstwy 'boundary_voivodeship', używam domyślnej...")
        tags = {"boundary": "administrative", "admin_level": "4"}
    else:
        tags = layer.get("tags", {})

    print("📥 Pobieram granice województw z OSM (Poland bbox, kafelkowanie)...")

    max_area = config.get('osmnx_settings', {}).get('max_query_area_size', 500000000)
    
    w, s, e, n = poland_bbox
    lat_mid = (s + n) / 2.0
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_mid))
    area = (e - w) * m_per_deg_lon * (n - s) * m_per_deg_lat

    print(f"📐 Całkowity obszar: {area/1e6:.2f} km²")

    if area <= max_area:
        tiles = [poland_bbox]
        print(f"✅ Obszar mieści się w jednym zapytaniu")
    else:
        n_tiles = max(2, int(math.ceil(math.sqrt(area / max_area))))
        tiles = []
        lon_step = (e - w) / n_tiles
        lat_step = (n - s) / n_tiles
        for i in range(n_tiles):
            for j in range(n_tiles):
                tiles.append((
                    w + i * lon_step,
                    s + j * lat_step,
                    w + (i + 1) * lon_step,
                    s + (j + 1) * lat_step
                ))
        print(f"⚠️  Podzielono na {n_tiles}x{n_tiles} = {len(tiles)} kafli")

    servers = config.get('overpass_servers', [])
    if not servers:
        print("❌ Brak serwerów Overpass w konfiguracji!")
        sys.exit(1)
    
    n_servers = len(servers)
    frames = []
    
    print(f"\n🔄 Rozpoczynam pobieranie {len(tiles)} kafli:\n")

    for i, tile_bbox in enumerate(tiles, 1):
        server = servers[i % n_servers]
        
        print(f"🧩 Kafelek {i}/{len(tiles)}")
        print(f"   🌐 Serwer: {server}")
        
        try:
            ox.settings.overpass_endpoint = server
            
            gdf = ox.features_from_bbox(bbox=tile_bbox, tags=tags)
            
            if 'admin_level' in gdf.columns:
                gdf = gdf[gdf['admin_level'] == '4']
            
            if not gdf.empty:
                frames.append(gdf)
                print(f"   ✅ Pobrano {len(gdf)} obiektów")
            else:
                print(f"   ℹ️  Brak danych w tym kaflu")
                
        except Exception as e:
            print(f"   ⚠️  Błąd pobierania kafla: {e}")

        if i < len(tiles):
            sleep_range = config.get('download_settings', {}).get('sleep_between_tiles', [2, 4])
            sleep_time = random.uniform(*sleep_range)
            time.sleep(sleep_time)

    if not frames:
        print("❌ Nie udało się pobrać żadnych danych granic województw")
        sys.exit(1)

    print(f"\n🔄 Łączenie {len(frames)} fragmentów...")
    final_gdf = pd.concat(frames, ignore_index=True)
    
    if 'osmid' in final_gdf.columns:
        final_gdf = final_gdf.drop_duplicates(subset=['osmid'])
    
    # ========== FILTROWANIE TYLKO POLSKICH WOJEWÓDZTW ==========
    print(f"🔍 Filtruję tylko polskie województwa...")
    
    polish_voivodeships = final_gdf.copy()
    
    # Filtruj po nazwie zawierającej "województwo"
    if 'name' in polish_voivodeships.columns:
        polish_voivodeships = polish_voivodeships[
            polish_voivodeships['name'].str.contains('województwo', case=False, na=False)
        ]
    
    # Dodatkowo sprawdź ISO3166-2 dla Polski (opcjonalnie)
    if 'ISO3166-2' in polish_voivodeships.columns:
        polish_voivodeships = polish_voivodeships[
            polish_voivodeships['ISO3166-2'].str.startswith('PL-', na=False) |
            polish_voivodeships['name'].str.contains('województwo', case=False, na=False)
        ]
    
    if polish_voivodeships.empty:
        print("❌ Nie znaleziono polskich województw po filtrowaniu!")
        sys.exit(1)
    
    print(f"✅ Znaleziono {len(polish_voivodeships)} polskich województw")
    # ===========================================================
    
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    polish_voivodeships.to_file(filepath, driver='GeoJSON')
    print(f"✅ Zapisano {len(polish_voivodeships)} województw do: {filepath}\n")

def get_voivodeship_geometry(filepath, region_name):
    """Pobiera geometrię województwa wg nazwy."""
    gdf = gpd.read_file(filepath)
    
    region_gdf = gdf[gdf['name'].str.lower() == region_name.lower()]
    
    if region_gdf.empty:
        if 'official_name' in gdf.columns:
            region_gdf = gdf[gdf['official_name'].str.lower().str.contains(region_name.lower(), na=False)]
    
    if region_gdf.empty:
        raise Exception(f"Nie znaleziono województwa '{region_name}' w pliku granic")
    
    return region_gdf.iloc[0].geometry

# ============================================================================
# FUNKCJE POMOCNICZE DO NAZW
# ============================================================================

def get_friendly_type(layer_name, config=None):
    """Konwertuje techniczne nazwy warstw na przyjazne dla użytkownika."""
    default_mapping = {
        'man_made_chimney': 'Komin',
        'man_made_tower': 'Wieża',
        'man_made_mast': 'Maszt',
        'power_line': 'Linia energetyczna',
        'power_tower': 'Słup energetyczny',
        'waterway_river': 'Rzeka',
        'waterway_stream': 'Strumień',
        'boundary_national': 'Granica państwa',
    }
    
    if config and 'layer_names_pl' in config:
        type_mapping = config['layer_names_pl']
    else:
        type_mapping = default_mapping
    
    friendly_name = type_mapping.get(layer_name)
    
    if friendly_name:
        return friendly_name
    else:
        return layer_name.replace('_', ' ').title()

def create_smart_name(row, idx, layer_name, config=None):
    """Tworzy inteligentną nazwę z dostępnych danych OSM."""
    
    if 'name' in row and not pd.isna(row['name']):
        name_val = str(row['name']).strip()
        if name_val and name_val.lower() not in ['unnamed', 'unknown', 'null', 'none', '']:
            return name_val
    
    if 'operator' in row and not pd.isna(row['operator']):
        operator_val = str(row['operator']).strip()
        if operator_val and operator_val.lower() not in ['unknown', 'null', 'none', '']:
            obj_type = get_friendly_type(layer_name, config)
            return f"{operator_val} - {obj_type}"
    
    if 'brand' in row and not pd.isna(row['brand']):
        brand_val = str(row['brand']).strip()
        if brand_val:
            return brand_val
    
    addr_parts = []
    if 'addr:street' in row and not pd.isna(row['addr:street']):
        addr_parts.append(str(row['addr:street']))
    if 'addr:housenumber' in row and not pd.isna(row['addr:housenumber']):
        addr_parts.append(str(row['addr:housenumber']))
    
    if len(addr_parts) == 2:
        return ', '.join(addr_parts)
    
    if 'addr:street' in row and not pd.isna(row['addr:street']):
        street = str(row['addr:street']).strip()
        if street:
            obj_type = get_friendly_type(layer_name, config)
            return f"{obj_type} - ul. {street}"
    
    if 'addr:city' in row and not pd.isna(row['addr:city']):
        city = str(row['addr:city']).strip()
        if city:
            obj_type = get_friendly_type(layer_name, config)
            return f"{obj_type} - {city}"
    
    if 'ref' in row and not pd.isna(row['ref']):
        ref_val = str(row['ref']).strip()
        if ref_val:
            return f"Ref: {ref_val}"
    
    if 'description' in row and not pd.isna(row['description']):
        desc = str(row['description']).strip()
        if desc and len(desc) < 50:
            return desc
    
    for col in ['addr:place', 'addr:village', 'addr:hamlet', 'addr:suburb']:
        if col in row and not pd.isna(row[col]):
            place = str(row[col]).strip()
            if place:
                obj_type = get_friendly_type(layer_name, config)
                return f"{obj_type} - {place}"
    
    if 'height' in row and not pd.isna(row['height']):
        try:
            height = float(row['height'])
            if height > 10:
                obj_type = get_friendly_type(layer_name, config)
                return f"{obj_type} {height:.0f}m"
        except:
            pass
    
    try:
        geom = row.geometry
        if geom and geom.geom_type == 'Point':
            obj_type = get_friendly_type(layer_name, config)
            return f"{obj_type} ({geom.y:.5f}, {geom.x:.5f})"
        elif geom:
            centroid = geom.centroid
            obj_type = get_friendly_type(layer_name, config)
            return f"{obj_type} ({centroid.y:.5f}, {centroid.x:.5f})"
    except:
        pass
    
    obj_type = get_friendly_type(layer_name, config)
    return f"{obj_type} #{idx}"

def create_description(row):
    """Tworzy bogaty opis z dostępnych atrybutów OSM."""
    desc_lines = []
    
    priority_fields = [
        ('name', '🏷️ Nazwa'),
        ('operator', '🏢 Operator'),
        ('brand', '🏪 Marka'),
        ('addr:street', '📍 Ulica'),
        ('addr:housenumber', '🏠 Nr domu'),
        ('addr:city', '🏙️ Miasto'),
        ('addr:postcode', '📮 Kod pocztowy'),
        ('height', '📏 Wysokość'),
        ('ele', '⛰️ Wysokość npm'),
        ('voltage', '⚡ Napięcie'),
        ('ref', '🔢 Numer ref'),
        ('material', '🧱 Materiał'),
        ('description', '📝 Opis'),
        ('website', '🌐 Strona WWW'),
        ('phone', '📞 Telefon'),
    ]
    
    for field, label in priority_fields:
        if field in row and not pd.isna(row[field]):
            value = str(row[field])
            if field == 'voltage':
                try:
                    voltage_v = float(value)
                    if voltage_v >= 1000:
                        value = f"{voltage_v/1000:.0f} kV"
                    else:
                        value = f"{voltage_v} V"
                except:
                    pass
            elif field == 'height':
                value = f"{value} m"
            
            desc_lines.append(f"{label}: {value}")
    
    if desc_lines:
        desc_lines.append("─" * 40)
    
    skip_fields = {'geometry', 'name', 'operator', 'brand', 'addr:street', 
                  'addr:housenumber', 'addr:city', 'addr:postcode',
                  'height', 'ele', 'voltage', 'ref', 'material', 
                  'description', 'website', 'phone'}
    
    other_fields = []
    for col in row.index:
        if col not in skip_fields and not pd.isna(row[col]):
            value = str(row[col])
            if len(value) < 100:
                other_fields.append(f"{col}: {value}")
    
    if other_fields:
        desc_lines.append("🔍 Dodatkowe informacje:")
        desc_lines.extend(other_fields[:10])
    
    return "\n".join(desc_lines) if desc_lines else "Brak szczegółowych informacji"

# ============================================================================
# KONWERSJA DO KMZ
# ============================================================================

def geojson_to_kmz(geojson_path, layer_name, kmz_dir, style_config=None, 
                   name_suffix=None, no_date=False, config=None):
    """Konwertuje plik GeoJSON do KMZ z bogatymi informacjami z OSM."""
    try:
        gdf = gpd.read_file(geojson_path)
        
        if gdf.empty:
            return False, None
        
        kml = simplekml.Kml()
        
        if name_suffix:
            if '_' in name_suffix:
                region_name = name_suffix.split('_')[0]
            else:
                region_name = name_suffix
            kml.document.name = f"{layer_name} - {region_name}"
        else:
            kml.document.name = layer_name
        
        style = style_config or {}
        color = style.get('color', 'ff0000ff')
        width = style.get('width', 2)
        fill_color = style.get('fillColor', '33ffffff')
        
        def convert_color(argb_color):
            if len(argb_color) == 8:
                return argb_color
            return 'ffffffff'
        
        kml_color = convert_color(color)
        kml_fill_color = convert_color(fill_color)
        
        for idx, row in gdf.iterrows():
            geom = row.geometry
            name = create_smart_name(row, idx, layer_name, config)
            description = create_description(row)
            
            if geom.geom_type in ['LineString', 'MultiLineString']:
                if geom.geom_type == 'MultiLineString':
                    coords_list = [list(line.coords) for line in geom.geoms]
                else:
                    coords_list = [list(geom.coords)]
                
                for coords in coords_list:
                    line = kml.newlinestring(name=str(name), description=description)
                    line.coords = [(lon, lat) for lon, lat in coords]
                    line.style.linestyle.color = kml_color
                    line.style.linestyle.width = width
            
            elif geom.geom_type == 'Point':
                pnt = kml.newpoint(name=str(name), description=description)
                pnt.coords = [(geom.x, geom.y)]
                pnt.style.iconstyle.color = kml_color
            
            elif geom.geom_type in ['Polygon', 'MultiPolygon']:
                if geom.geom_type == 'MultiPolygon':
                    polygons = list(geom.geoms)
                else:
                    polygons = [geom]
                
                for poly in polygons:
                    pol = kml.newpolygon(name=str(name), description=description)
                    pol.outerboundaryis = list(poly.exterior.coords)
                    
                    if poly.interiors:
                        pol.innerboundaryis = [list(interior.coords) for interior in poly.interiors]
                    
                    pol.style.linestyle.color = kml_color
                    pol.style.linestyle.width = 1
                    pol.style.polystyle.color = kml_fill_color
                    pol.style.polystyle.fill = 1
                    pol.style.polystyle.outline = 1
        
        name_parts = [layer_name]
        if name_suffix:
            name_parts.append(name_suffix)
        
        filename = '-'.join(name_parts) + '.kmz'
        kmz_path = os.path.join(kmz_dir, filename)
        
        kml.savekmz(kmz_path)
        return True, filename
        
    except Exception as e:
        print(f"❌ Błąd konwersji {geojson_path} → KMZ: {e}")
        import traceback
        traceback.print_exc()
        return False, None

# ============================================================================
# KLASY POMOCNICZE
# ============================================================================

class LogHandler(logging.Handler):
    """Przekierowuje logi z OSMnx do zdefiniowanego callbacka."""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        msg = self.format(record)
        if self.callback:
            self.callback(f"[OSMnx] {msg}")

# ============================================================================
# GŁÓWNA KLASA DOWNLOADERA
# ============================================================================

class OSMDownloader:
    """Pobiera dane OSM z auto-ponawianiem, ochroną rate-limit i rotacją serwerów."""
    
    def __init__(self, config, layers_dict=None, progress_callback=None, 
                 log_callback=None, stop_flag=None, name_suffix=None, no_date=False):
        self.config = config
        self.layers_dict = layers_dict or {}
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.stop_flag = stop_flag
        self.name_suffix = name_suffix
        self.no_date = no_date
        self._setup_osmnx()
        self._setup_logging()

    def _setup_osmnx(self):
        """Konfiguruje globalne ustawienia OSMnx."""
        settings = self.config.get('osmnx_settings', {})
        
        for key, value in settings.items():
            try:
                setattr(ox.settings, key, value)
            except Exception:
                pass
        
        ox.settings.overpass_rate_limit = True
        ox.settings.retry_on_timeout = True
        ox.settings.overpass_pause = settings.get('overpass_pause', 5)
        ox.settings.use_cache = settings.get('use_cache', True)
        ox.settings.cache_folder = settings.get('cache_folder', 'overpass_cache')
        ox.settings.max_query_area_size = settings.get('max_query_area_size', 500000000)
        ox.settings.timeout = settings.get('timeout', 180)
        
        self.log(f"🔧 OSMnx skonfigurowany")
        self.log(f"   Max obszar zapytania: {ox.settings.max_query_area_size / 1e6} km²")
        self.log(f"   Timeout: {ox.settings.timeout}s")

    def _setup_logging(self):
        """Konfiguruje przechwytywanie logów z OSMnx."""
        if self.log_callback:
            self.log_handler = LogHandler(self.log_callback)
            self.log_handler.setFormatter(logging.Formatter('%(message)s'))
            osmnx_logger.addHandler(self.log_handler)
            osmnx_logger.setLevel(logging.DEBUG)

    def log(self, msg):
        """Loguje wiadomość z timestampem."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] {msg}"
        
        if self.log_callback:
            self.log_callback(full_msg)
        else:
            print(full_msg)

    def update_progress(self, current, total, name=""):
        """Aktualizuje pasek postępu."""
        if self.progress_callback:
            self.progress_callback(current, total, name)

    def close_session(self):
        """Zamyka sesję HTTP w OSMnx."""
        try:
            if hasattr(ox, '_session'):
                ox._session.close()
                delattr(ox, '_session')
        except Exception:
            pass

    def cleanup_logging(self):
        """Usuwa handler logów."""
        if hasattr(self, 'log_handler'):
            osmnx_logger.removeHandler(self.log_handler)

    def fetch_layer(self, name, tags, polygon_geom, geojson_temp_dir, kmz_dir, style_config=None):
        """Pobiera pełną warstwę - dzieli duży polygon na kafle z postępem."""
        servers = self.config.get('overpass_servers', [])
        if not servers:
            self.log("❌ Brak serwerów Overpass!")
            return False

        download_settings = self.config.get('download_settings', {})
        max_attempts = download_settings.get('max_attempts', 3)
        
        self.log(f"\n📥 Warstwa: '{name}' (dokładny kształt województwa)")

        # Oblicz ile kafli będzie potrzebnych
        bounds = polygon_geom.bounds  # (minx, miny, maxx, maxy)
        w, s, e, n = bounds
        
        lat_mid = (s + n) / 2.0
        m_per_deg_lat = 111320.0
        m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_mid))
        area = (e - w) * m_per_deg_lon * (n - s) * m_per_deg_lat
        
        max_area = self.config.get('osmnx_settings', {}).get('max_query_area_size', 500000000)
        
        self.log(f"📐 Obszar województwa: {area/1e6:.2f} km²")
        
        if area <= max_area:
            n_tiles = 1
            tiles = [polygon_geom]
            self.log(f"✅ Obszar mieści się w jednym zapytaniu")
        else:
            n_tiles = max(2, int(math.ceil(math.sqrt(area / max_area))))
            self.log(f"⚠️  Podzielę na siatkę {n_tiles}x{n_tiles} kafli")
            
            # Podziel bbox na kafle
            lon_step = (e - w) / n_tiles
            lat_step = (n - s) / n_tiles
            
            tiles = []
            for i in range(n_tiles):
                for j in range(n_tiles):
                    tile_box = box(
                        w + i * lon_step,
                        s + j * lat_step,
                        w + (i + 1) * lon_step,
                        s + (j + 1) * lat_step
                    )
                    # Przecięcie z oryginalnym polygonem województwa
                    tile_poly = polygon_geom.intersection(tile_box)
                    if not tile_poly.is_empty:
                        tiles.append(tile_poly)
            
            self.log(f"📊 Utworzono {len(tiles)} kafli do pobrania\n")

        # Pobierz każdy kafelek z postępem
        frames = []
        for i, tile_geom in enumerate(tiles, 1):
            self.log(f"🧩 Kafelek {i}/{len(tiles)}")
            
            for attempt in range(1, max_attempts + 1):
                if self.stop_flag and getattr(self.stop_flag, "value", False):
                    break

                current_server = servers[(i + attempt) % len(servers)]
                self.log(f"   🌐 Serwer: {current_server} (próba {attempt}/{max_attempts})")

                try:
                    ox.settings.overpass_endpoint = current_server
                    self.close_session()

                    gdf = ox.features_from_polygon(tile_geom, tags)

                    if not gdf.empty:
                        frames.append(gdf)
                        self.log(f"   ✅ Pobrano {len(gdf)} obiektów")
                        break
                    else:
                        self.log(f"   ℹ️  Brak danych w tym kaflu")
                        break
                        
                except Exception as e:
                    error_msg = str(e).lower()
                    self.log(f"   ⚠️  Błąd: {type(e).__name__}")
                    
                    if "504" in error_msg or "timeout" in error_msg:
                        wait_time = download_settings.get('sleep_on_timeout', 30)
                    elif "rate limit" in error_msg or "429" in error_msg:
                        wait_time = download_settings.get('sleep_on_rate_limit', 45)
                    else:
                        wait_time = download_settings.get('sleep_on_error', 10)
                    
                    if attempt < max_attempts:
                        self.log(f"   ⏳ Czekam {wait_time}s...")
                        time.sleep(wait_time)
            
            # Pauza między kaflami
            if i < len(tiles):
                sleep_range = download_settings.get('sleep_between_tiles', [2, 4])
                time.sleep(random.uniform(*sleep_range))

        if not frames:
            self.log(f"❌ Brak danych dla '{name}'")
            return False

        # Łączenie fragmentów
        self.log(f"\n🔄 Łączenie {len(frames)} fragmentów...")
        final_gdf = pd.concat(frames, ignore_index=True)
        
        # Usuń duplikaty
        if 'osmid' in final_gdf.columns:
            final_gdf = final_gdf.drop_duplicates(subset=['osmid'])
            self.log(f"✅ Po usunięciu duplikatów: {len(final_gdf)} obiektów")

        os.makedirs(geojson_temp_dir, exist_ok=True)
        geojson_path = os.path.join(geojson_temp_dir, f"{name}.geojson")
        final_gdf.to_file(geojson_path, driver="GeoJSON")
        self.log(f"✅ Zapisano {len(final_gdf)} obiektów do tymczasowego GeoJSON")

        os.makedirs(kmz_dir, exist_ok=True)
        self.log(f"🔄 Konwersja do KMZ...")

        success, filename = geojson_to_kmz(
            geojson_path, name, kmz_dir, style_config,
            name_suffix=self.name_suffix,
            no_date=self.no_date,
            config=self.config
        )

        if success:
            self.log(f"✅ Zapisano KMZ: {filename}")

            output_settings = self.config.get('output_settings', {})
            keep_geojson = output_settings.get('keep_geojson', False)

            if not keep_geojson:
                try:
                    os.remove(geojson_path)
                    self.log(f"🗑️  Usunięto tymczasowy GeoJSON")
                except Exception as e:
                    self.log(f"⚠️  Nie udało się usunąć GeoJSON: {e}")
            else:
                self.log(f"📄 Zachowano GeoJSON: {geojson_path}")
        else:
            self.log(f"❌ Nie udało się utworzyć KMZ")
            return False

        self.log("")
        return True



    def download_layers(self, layer_names, region_name=None, bbox=None):
        """Pobiera wszystkie warstwy dla województwa (polygon) lub bbox."""
        succeeded, failed = [], []

        directories = self.config.get('directories', {})
        kmz_dir = directories.get('kmz', 'KMZ/OSM')
        geojson_temp_dir = directories.get('geojson_temp', 'OSM_Data/geojson_temp')

        if region_name:
            voiv_geojson = os.path.join(geojson_temp_dir, 'voivodeships.geojson')
            
            poland_bbox = (14.1, 49.0, 24.2, 54.9)
            fetch_save_voivodeships_geojson(voiv_geojson, self.layers_dict, poland_bbox, self.config)
            
            try:
                polygon_geom = get_voivodeship_geometry(voiv_geojson, region_name)
                self.log(f"\n{'='*60}\n📋 Pobieranie warstw OSM dla województwa {region_name}\n{'='*60}")
                
                # Ustaw sufiks na nazwę województwa (bez słowa "województwo")
                region_short = region_name.replace('województwo ', '').strip()
                self.name_suffix = region_short
                
            except Exception as e:
                self.log(f"❌ Błąd pobierania geometrii województwa: {e}")
                return [], layer_names
        elif bbox:
            polygon_geom = box(bbox[0], bbox[1], bbox[2], bbox[3])
            self.log(f"\n{'='*60}\n📋 Pobieranie warstw OSM (bbox)\n{'='*60}")
        else:
            self.log("❌ Nie podano ani region_name ani bbox!")
            return [], layer_names

        self.log(f"📂 KMZ: {kmz_dir}")
        self.log(f"📂 Temp GeoJSON: {geojson_temp_dir}")

        if self.name_suffix:
            self.log(f"📝 Sufiks nazwy: '{self.name_suffix}'")
        if self.no_date:
            self.log(f"📅 Wyłączono dodawanie daty")

        for i, name in enumerate(layer_names, 1):
            if name not in self.layers_dict:
                self.log(f"❌ Warstwa '{name}' nie istnieje")
                failed.append(name)
                continue

            self.log(f"\n--- [{i}/{len(layer_names)}] {name} ---")
            layer_config = self.layers_dict[name]
            tags = layer_config.get("tags", {})
            style = layer_config.get("style", {})

            if self.fetch_layer(name, tags, polygon_geom, geojson_temp_dir, kmz_dir, style):
                succeeded.append(name)
            else:
                failed.append(name)

            if i < len(layer_names):
                sleep_range = self.config.get('download_settings', {}).get('sleep_between_layers', [3, 5])
                time.sleep(random.uniform(*sleep_range))

        self.log(f"\n{'='*60}\n✅ PODSUMOWANIE\n{'='*60}")
        self.log(f"Pobrano: {len(succeeded)}/{len(layer_names)}")
        if failed:
            self.log(f"Błędy: {', '.join(failed)}")
        self.log(f"📦 Pliki KMZ: {kmz_dir}")

        return succeeded, failed


# ============================================================================
# CLI
# ============================================================================

def parse_arguments():
    """Parsuje argumenty linii poleceń."""
    parser = argparse.ArgumentParser(
        description='OSM Downloader - precyzyjne pobieranie danych wg granic województw',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady użycia:
  %(prog)s -c config.json --region Dolnoslaskie --layers railways_main
  %(prog)s -c config.json --region all --layers railways_main
  %(prog)s -c config.json --bbox 20.71 52.08 21.42 52.39 --layers boundary_national
  %(prog)s -c config.json --list-layers
        """
    )

    parser.add_argument('-c', '--config', type=str, required=True, help='Ścieżka do pliku config.json')
    parser.add_argument('--layer-file', type=str, nargs='+', default=None, help='Pliki JSON z warstwami')
    parser.add_argument('--layers', nargs='+', default=None, help='Lista warstw do pobrania')
    parser.add_argument('--region', type=str, default=None, help='Nazwa województwa, lista (przecinkami) lub "all"')
    parser.add_argument('--bbox', type=float, nargs=4, metavar=('W', 'S', 'E', 'N'), default=None, help='Bounding box')
    parser.add_argument('--name-suffix', type=str, default=None, help='Sufiks nazwy pliku')
    parser.add_argument('--no-date', action='store_true', help='Wyłącz datę w nazwie')
    parser.add_argument('--list-layers', action='store_true', help='Wyświetl warstwy')

    return parser.parse_args()

def load_multiple_layer_files(layer_files):
    """Wczytuje warstwy z wielu plików JSON."""
    all_layers = {}
    print(f"\n📂 Wczytywanie warstw z {len(layer_files)} plików:")
    for layer_file in layer_files:
        try:
            layers = load_layers_from_file(layer_file)
            if layers:
                all_layers.update(layers)
                print(f"   ✅ {layer_file}: {len(layers)} warstw")
        except Exception as e:
            print(f"   ❌ {layer_file}: {e}")
    print(f"\n📊 Łącznie załadowano {len(all_layers)} warstw\n")
    return all_layers

def main():
    args = parse_arguments()
    config = load_config(args.config)

    if args.layer_file:
        if isinstance(args.layer_file, list):
            layers_dict = load_multiple_layer_files(args.layer_file)
        else:
            layers_dict = load_layers_from_file(args.layer_file)
    else:
        layers_dict = discover_layer_files(config)

    if not layers_dict:
        print("❌ Nie załadowano żadnych warstw!")
        sys.exit(1)

    if args.list_layers:
        print(f"\n📋 Dostępne warstwy ({len(layers_dict)}):\n")
        for name, layer_config in layers_dict.items():
            desc = layer_config.get('description', 'Brak opisu')
            print(f"  • {name:30s} - {desc}")
        print()
        sys.exit(0)

    bbox = tuple(args.bbox) if args.bbox else None

    layers_to_download = args.layers if args.layers else list(layers_dict.keys())

    directories = config.get('directories', {})
    kmz_dir = directories.get('kmz', 'KMZ/OSM')

    print(f"\n🗺️  OSM Downloader + KMZ Converter")
    
    region_names = []
    if args.region:
        if args.region.strip().lower() == 'all':
            voiv_geojson = os.path.join(
                config.get('directories', {}).get('geojson_temp', 'OSM_Data/geojson_temp'),
                'voivodeships.geojson'
            )
            poland_bbox = (14.1, 49.0, 24.2, 54.9)
            if not os.path.exists(voiv_geojson):
                fetch_save_voivodeships_geojson(voiv_geojson, layers_dict, poland_bbox, config)
            
            # Wczytaj i upewnij się, że są to POLSKIE województwa
            gdf = gpd.read_file(voiv_geojson)
            
            # Filtruj polskie województwa
            if 'name' in gdf.columns:
                polish_gdf = gdf[gdf['name'].str.contains('województwo', case=False, na=False)]
            else:
                polish_gdf = gdf
            
            region_names = list(polish_gdf['name'].dropna().unique())
            
            print(f"📍 Wszystkie polskie województwa ({len(region_names)}): {', '.join(sorted(region_names))}")
        else:
            region_names = [r.strip() for r in args.region.split(',')]
            print(f"📍 Województwa: {', '.join(region_names)} (dokładny kształt)")
    elif bbox:
        print(f"📍 Bbox: {bbox}")

    print(f"📂 KMZ Output: {kmz_dir}")
    print(f"📋 Warstwy: {', '.join(layers_to_download)}")

    if args.name_suffix:
        print(f"📝 Sufiks: '{args.name_suffix}'")
    if args.no_date:
        print(f"📅 Bez daty")
    print()

    downloader = OSMDownloader(
        config, layers_dict,
        name_suffix=args.name_suffix,
        no_date=args.no_date
    )

    start_time = time.time()
    succeeded_total = []
    failed_total = []

    if region_names:
        for region_name in region_names:
            succeeded, failed = downloader.download_layers(layers_to_download, region_name=region_name)
            succeeded_total.extend(succeeded)
            failed_total.extend(failed)
    else:
        succeeded, failed = downloader.download_layers(layers_to_download, bbox=bbox)
        succeeded_total.extend(succeeded)
        failed_total.extend(failed)

    elapsed = time.time() - start_time

    print(f"\n⏱  Czas: {elapsed/60:.1f} min")
    print(f"✅ Pobrano: {len(succeeded_total)}")
    print(f"❌ Błędy: {len(failed_total)}")
    print(f"📦 Format: KMZ\n")

    sys.exit(0 if not failed_total else 1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Przerwano (Ctrl+C)")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Błąd: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
