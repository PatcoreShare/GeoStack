import click
import os
import sys
import json
from datetime import datetime
from src.storage import MBTilesStorage
from src.downloader import run_downloader
from src.utils import get_tiles_list, estimate_size

CONFIG_FILE = 'config.json'

def load_osm_config():
    """Wczytuje config OSM (tylko tiles_settings)."""
    if not os.path.exists(CONFIG_FILE):
        click.secho(f"❌ Błąd: Nie znaleziono {CONFIG_FILE}", fg='red')
        sys.exit(1)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data['tiles_settings']
    except json.JSONDecodeError as e:
        click.secho(f"❌ Błąd JSON w {CONFIG_FILE}: {e}", fg='red')
        sys.exit(1)
    except KeyError:
        click.secho("❌ Brak 'tiles_settings' w config.json", fg='red')
        sys.exit(1)

@click.command(help="""
Pobieranie OSM tiles do MBTiles.

Przykłady:
  python main.py -b 20.7 52.42 20.74 52.45 --min-zoom 10 --max-zoom 11
  python main.py --min-zoom 12 --max-zoom 14  # Używa domyślny bbox z config.json
""")
@click.option('--bbox', '-b', nargs=4, type=float, 
              help='Obszar: W S E N (west south east north)')
@click.option('--min-zoom', type=int, help='Minimalny zoom (domyślnie z config)')
@click.option('--max-zoom', type=int, help='Maksymalny zoom (domyślnie z config)')
@click.option('--output', '-o', help='Ścieżka do pliku MBTiles (auto z timestamp)')
def main(bbox, min_zoom, max_zoom, output):
    """Pobieranie OpenStreetMap tiles do formatu MBTiles."""
    
    # Wczytaj konfigurację
    config = load_osm_config()
    
    # Ustaw parametry (CLI > config)
    bbox = bbox or [
        config['bbox']['west'], config['bbox']['south'], 
        config['bbox']['east'], config['bbox']['north']
    ]
    min_zoom = min_zoom or config['zoom_levels']['min']
    max_zoom = max_zoom or config['zoom_levels']['max']
    
    # Walidacja
    if min_zoom > max_zoom:
        click.secho("❌ min-zoom nie może być większy niż max-zoom", fg='red')
        return
    if min_zoom < 0 or max_zoom > 19:
        click.secho("❌ Zoom musi być w zakresie 0-19", fg='red')
        return
    
    # Nagłówek
    click.secho(f"=== OSM Tiles Downloader ===", fg='cyan', bold=True)
    click.echo(f"📍 Obszar: {bbox}")
    click.echo(f"🔍 Zoom: {min_zoom} → {max_zoom}")
    
    # Generowanie listy kafelków
    click.echo("📊 Generowanie listy kafelków...")
    all_tiles = []
    for z in range(min_zoom, max_zoom + 1):
        all_tiles.extend(get_tiles_list(bbox, z))
    
    total_count = len(all_tiles)
    click.echo(f"📦 Liczba kafelków: {total_count:,} (~{estimate_size(total_count)})")
    
    if total_count == 0:
        click.secho("❌ Brak kafelków dla podanego obszaru", fg='red')
        return
    
    if total_count > 50000:
        if not click.confirm('⚠️  Duża ilość danych. Kontynuować?', default=False):
            return
    
    # Ścieżka wyjściowa
    if not output:
        ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
        output = f"data/osm_z{min_zoom}-{max_zoom}_{ts}.mbtiles"
    
    # Utwórz katalog
    os.makedirs(os.path.dirname(output), exist_ok=True)
    
    click.echo(f"💾 Zapis do: {output}")
    
    # Pobieranie i zapis
    try:
        with MBTilesStorage(output) as storage:
            # Metadane
            storage.save_metadata(
                name=config['mbtiles_settings']['name'],
                description=f"OSM {min_zoom}-{max_zoom} | Bbox: {bbox}",
                bounds_str=",".join(map(str, bbox)),
                fmt='png'
            )
            
            # Pobieranie
            run_downloader(all_tiles, storage, config)
        
        file_size = os.path.getsize(output) / (1024*1024)
        click.secho(f"\n✅ GOTOWE! {output} ({file_size:.1f} MB)", fg='green', bold=True)
        
    except Exception as e:
        click.secho(f"\n❌ BŁĄD: {e}", fg='red')
        import traceback
        click.secho(traceback.format_exc(), fg='yellow')

if __name__ == '__main__':
    main()
