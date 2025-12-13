import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from .utils import flip_y


def fetch_tile_content(tile, url_template, headers, timeout):
    url = url_template.format(z=tile.z, y=tile.y, x=tile.x)
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            if b'ServiceException' in resp.content or b'<html' in resp.content[:50]:
                return tile, None, None
            return tile, resp.content, None
        else:
            return tile, None, None
    except Exception as e:
        return tile, None, str(e)


def run_downloader(tiles_list, storage_instance, config):
    total = len(tiles_list)

    template = config['url_template']
    headers = config['headers']
    timeout = config.get('timeout', 10)
    workers = config.get('workers', 4)

    print(f"Start pobierania {total} kafelków, workers={workers}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_tile = {
            executor.submit(fetch_tile_content, tile, template, headers, timeout): tile
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
                    print(f"Błąd przy kafelku {tile_xyz.z}/{tile_xyz.x}/{tile_xyz.y}: {error_msg}", flush=True)

            processed += 1

            if processed % 200 == 0:
                storage_instance.commit()
                print(f"Pobrano {processed}/{total} kafelków (błędów: {errors_count})", flush=True)

        storage_instance.commit()
        print(f"Zakończono pobieranie: {processed}/{total}, błędów: {errors_count}", flush=True)

        if errors_count > 0:
            print(f"Uwaga: {errors_count} kafelków nie udało się pobrać.", flush=True)
