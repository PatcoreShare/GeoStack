import click
import os
import sys
import json
from datetime import datetime

# Dodajemy bieżący katalog do ścieżki
sys.path.append(os.getcwd())

from src.storage import MBTilesStorage
from src.downloader import run_downloader
from src.utils import get_tiles_list, estimate_size

CONFIG_FILE = 'config.json'


def load_base_config():
    """Wczytuje tylko surowy JSON."""
    if not os.path.exists(CONFIG_FILE):
        click.secho(f"Błąd: Nie znaleziono pliku {CONFIG_FILE}", fg='red')
        sys.exit(1)
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_layer_config(json_data, layer_key):
    """Przygotowuje konfigurację dla konkretnej warstwy."""
    app_settings = json_data.get('app_settings', {})
    layers = json_data.get('layers', {})

    if layer_key not in layers:
        return None

    layer_conf = layers[layer_key]

    # Budowanie URL Template
    url_template = (
        f"{layer_conf['url_base']}"
        "?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        f"&LAYER={layer_conf['layer_param']}&STYLE=default&FORMAT={layer_conf['format']}"
        "&TILEMATRIXSET=EPSG:3857&TILEMATRIX=EPSG:3857:{z}"
        "&TILEROW={y}&TILECOL={x}"
    )

    return {
        'download_config': {
            'url_template': url_template,
            'headers': {
                'User-Agent': app_settings.get('user_agent', 'Mozilla/5.0'),
                'Accept': layer_conf['format']
            },
            'timeout': app_settings.get('request_timeout', 10),
            'workers': app_settings.get('max_workers', 4)
        },
        'layer_name': layer_conf.get('name', layer_key),
        'layer_key': layer_key,
        'format': layer_conf['format']
    }


# Wczytanie domyślnych wartości dla CLI (bbox/zoom)
_DEF_BBOX = [21.0, 52.2, 21.01, 52.23]
_DEF_MIN_Z = 1
_DEF_MAX_Z = 16

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'r') as f:
            _d = json.load(f)
            _app = _d.get('app_settings', {})
            _DEF_BBOX = _app.get('default_bbox', _DEF_BBOX)
            _DEF_MIN_Z = _app.get('default_min_zoom', _DEF_MIN_Z)
            _DEF_MAX_Z = _app.get('default_max_zoom', _DEF_MAX_Z)
    except:
        pass


@click.command(help="""
Pobieranie JEDNEJ warstwy z Geoportalu do pliku MBTiles.

Przykłady:
  python main.py --layer ORTO_STD
  python main.py -l UZBROJENIE --min-zoom 18 --max-zoom 19
  python main.py -l TOPO -b 20.65 52.41 20.76 52.46

Dostępne warstwy (klucze) znajdziesz w config.json w sekcji "layers".
""")
@click.option(
    '--layer', '-l',
    required=True,
    help='Klucz warstwy z config.json (np. ORTO_STD, TOPO, UZBROJENIE). WYMAGANE.'
)
@click.option(
    '--bbox', '-b',
    nargs=4,
    type=float,
    default=tuple(_DEF_BBOX),
    help=f'Obszar: W S E N. Domyślnie: {_DEF_BBOX}'
)
@click.option(
    '--min-zoom',
    type=int,
    default=_DEF_MIN_Z,
    help=f'Min zoom (domyślnie: {_DEF_MIN_Z})'
)
@click.option(
    '--max-zoom',
    type=int,
    default=_DEF_MAX_Z,
    help=f'Max zoom (domyślnie: {_DEF_MAX_Z})'
)
@click.option(
    '--output', '-o',
    type=click.Path(),
    default=None,
    help='Ścieżka pliku wyjściowego. Jeśli puste -> data/<layer>.mbtiles'
)
def main(layer, bbox, min_zoom, max_zoom, output):
    """
    Pobieranie jednej warstwy z Geoportalu do formatu MBTiles.
    Konfiguracja warstw i domyślnych parametrów w pliku config.json.
    """

    # 1. Wczytujemy plik config
    json_data = load_base_config()
    available_layers = json_data.get('layers', {})

    clean_key = layer.upper()
    if clean_key not in available_layers:
        click.secho(f"❌ Błąd: Warstwa '{clean_key}' nie istnieje w config.json.", fg='red')
        click.secho(f"Dostępne warstwy: {', '.join(available_layers.keys())}", fg='yellow')
        # Wyświetl help i zakończ
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        return

    # 2. Ładujemy konfigurację tej konkretnej warstwy
    conf = get_layer_config(json_data, clean_key)

    # 3. Walidacja zoomów
    if min_zoom > max_zoom:
        click.secho("❌ Min zoom nie może być większy niż max zoom.", fg='red')
        return

    # 4. Obliczenie kafelków
    click.secho(f"--- GeoSatelita: pobieranie warstwy {conf['layer_name']} ({clean_key}) ---", fg='cyan', bold=True)
    click.echo(f"Obszar: {bbox}")
    click.echo(f"Zoom: {min_zoom} -> {max_zoom}")

    all_tiles = []
    click.echo("Generowanie listy kafelków...")
    for z in range(min_zoom, max_zoom + 1):
        all_tiles.extend(get_tiles_list(bbox, z))

    total_count = len(all_tiles)
    click.echo(f"Liczba kafelków: {total_count} (~{estimate_size(total_count)})")

    if total_count == 0:
        click.secho("❌ Obszar jest pusty (0 kafelków).", fg='red')
        return

    if total_count > 20000:
        click.confirm('Duża ilość danych. Kontynuować?', abort=True)

    # 5. Ścieżka wyjściowa
    if output is None:
        if not os.path.exists('data'):
            os.makedirs('data')
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
        output = os.path.join('data', f"{clean_key.lower()}_{timestamp}.mbtiles")


    # 6. Pobieranie
    try:
        if os.path.exists(output):
            click.secho(f"⚠️ Plik {output} istnieje - dane zostaną dopisane.", fg='yellow')

        with MBTilesStorage(output) as storage:
            img_fmt = 'png' if 'png' in conf['format'] else 'jpg'
            bounds_str = ",".join(map(str, bbox))

            storage.save_metadata(
                name=conf['layer_name'],
                description=f"Layer: {clean_key}, Zoom: {min_zoom}-{max_zoom}",
                bounds_str=bounds_str,
                fmt=img_fmt
            )

            run_downloader(all_tiles, storage, conf['download_config'])

        click.secho(f"\n✅ Sukces! Plik zapisany jako: {output}", fg='green')
    except Exception as e:
        click.secho(f"\n❌ Wystąpił błąd krytyczny: {e}", fg='red')


if __name__ == '__main__':
    # Jeśli użytkownik odpali tylko `python main.py` bez parametrów,
    # Click i tak wyświetli help, bo --layer jest required=True.
    main()
