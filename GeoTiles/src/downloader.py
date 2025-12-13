import requests
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from .utils import flip_y


def fetch_tile_content(tile, servers, headers, timeout):
    """Pobiera kafelek OSM z losowego serwera."""
    url = random.choice(servers).format(z=tile.z, y=tile.y, x=tile.x)
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            # OSM zwraca PNG, ale sprawdź nagłówek
            if resp.content.startswith(b'\x89PNG'):
                return tile, resp.content, None
        return tile, None, None
    except Exception as e:
        return tile, None, str(e)


def run_downloader(tiles_list, storage_instance, config):
    """Pobiera tiles OSM z wielowątkowością."""
    total = len(tiles_list)
    
    servers = config['tile_servers']
    headers = config['headers']
    timeout = config.get('timeout', 15)
    workers = config.get('workers', 8)
    
    print(f"Start pobierania {total} kafelków OSM, workers={workers}", flush=True)
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_tile = {
            executor.submit(fetch_tile_content, tile, servers, headers, timeout): tile
            for tile in tiles_list
        }
        
        errors_count = 0
        processed = 0
        
        for future in as_completed(future_to_tile):
            tile_xyz, content, error_msg = future.result()
            
            if content:
                y_tms = flip_y(tile_xyz.z, tile_xyz.y)
                storage_instance.save_tile(tile_xyz.z, tile_xyz.x, y_tms, content)
            else:
                errors_count += 1
                if error_msg:
                    print(f"Błąd OSM {tile_xyz.z}/{tile_xyz.x}/{tile_xyz.y}: {error_msg}", flush=True)
            
            processed += 1
            
            if processed % 200 == 0:
                storage_instance.commit()
                print(f"Pobrano {processed}/{total} kafelków OSM (błędów: {errors_count})", flush=True)
        
        storage_instance.commit()
        print(f"Zakończono OSM: {processed}/{total}, błędów: {errors_count}", flush=True)
        
        if errors_count > 0:
            print(f"Uwaga: {errors_count} kafelków OSM nie udało się pobrać.", flush=True)
