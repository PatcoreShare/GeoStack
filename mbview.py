import sqlite3
import uvicorn
import sys
import os
import glob
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse

app = FastAPI()

# Globalna zmienna na ścieżkę (ustawiana przy starcie)
MBTILES_PATH = ""

def get_db():
    conn = sqlite3.connect(MBTILES_PATH)
    return conn

@app.get("/{z}/{x}/{y}.jpg")
@app.get("/{z}/{x}/{y}.png") # Obsługa obu rozszerzeń
def get_tile(z: int, x: int, y: int):
    try:
        conn = get_db()
        cursor = conn.cursor()
        tms_y = (2**z - 1) - y
        cursor.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?", (z, x, tms_y))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # Wykrywanie typu obrazka (PNG/JPG) po nagłówku
            # PNG zaczyna się od bajtów: 89 50 4E 47
            # JPG zaczyna się od bajtów: FF D8 FF
            header = row[0][:4]
            mime = "image/png" if header.startswith(b'\x89PNG') else "image/jpeg"
            return Response(content=row[0], media_type=mime)
            
    except Exception as e:
        print(f"Error: {e}")
        
    return Response(status_code=404)

@app.get("/", response_class=HTMLResponse)
def index():
    # Pobieramy metadane z bazy, aby ustawić widok
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Zakres zoomów
    try:
        cursor.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles")
        min_z, max_z = cursor.fetchone()
        if min_z is None: min_z, max_z = 1, 18
    except: min_z, max_z = 1, 18
    
    # 2. Granice (Bounds)
    center_lat, center_lon = 52.0, 19.0
    try:
        cursor.execute("SELECT value FROM metadata WHERE name='bounds'")
        row = cursor.fetchone()
        if row:
            w, s, e, n = map(float, row[0].split(','))
            center_lat = (s + n) / 2
            center_lon = (w + e) / 2
    except: pass
    
    conn.close()

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>MBTiles Viewer: {os.path.basename(MBTILES_PATH)}</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body, html, #map {{ width: 100%; height: 100%; margin: 0; }}
            .zoom-display {{
                position: absolute; bottom: 20px; left: 20px;
                background: rgba(255, 255, 255, 0.9);
                padding: 10px 15px;
                border-radius: 5px; border: 2px solid #333;
                z-index: 1000; font-family: monospace; font-size: 14px; font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <div id="zoomInfo" class="zoom-display">Ładowanie...</div>

        <script>
            var dbMinZ = {min_z};
            var dbMaxZ = {max_z};

            var map = L.map('map', {{
                minZoom: dbMinZ,
                maxZoom: dbMaxZ  // NIE pozwól przybliżyć bardziej niż dane
            }}).setView([{center_lat}, {center_lon}], dbMinZ);

            L.tileLayer('/{{z}}/{{x}}/{{y}}.png', {{
                minZoom: dbMinZ,
                maxZoom: dbMaxZ,       // blokada zoomu
                maxNativeZoom: dbMaxZ, // brak overzoomingu
                tms: false,
                attribution: 'MBTiles Viewer'
            }}).addTo(map);

            var zoomInfo = document.getElementById('zoomInfo');

            function updateZoom() {{
                var z = map.getZoom();
                var statusColor = (z >= dbMinZ && z <= dbMaxZ) ? 'green' : 'red';
                var statusText = (z >= dbMinZ && z <= dbMaxZ) ? 'DANE DOSTĘPNE' : 'BRAK DANYCH';

                zoomInfo.innerHTML = `
                    Plik: {os.path.basename(MBTILES_PATH)}<br>
                    Zoom Mapy: ${{z}}<br>
                    Zoom Pliku: ${{dbMinZ}} - ${{dbMaxZ}}<br>
                    Status: <span style="color:${{statusColor}}">${{statusText}}</span>
                `;
                zoomInfo.style.borderColor = statusColor;
            }}

            map.on('zoomend', updateZoom);
            map.on('moveend', updateZoom);
            updateZoom();
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    # Logika wyboru pliku
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        # Automatyczne szukanie najnowszego pliku w data/
        list_of_files = glob.glob('data/*.mbtiles')
        if not list_of_files:
            print("❌ Błąd: Nie znaleziono żadnych plików .mbtiles w folderze data/")
            print("Użycie: python mbview.py sciezka/do/pliku.mbtiles")
            sys.exit(1)
        target = max(list_of_files, key=os.path.getctime)
        print(f"ℹ️ Nie podano pliku. Otwieram najnowszy znaleziony: {target}")

    if not os.path.exists(target):
        print(f"❌ Błąd: Plik {target} nie istnieje.")
        sys.exit(1)

    MBTILES_PATH = target
    
    print(f"🌍 Serwer startuje dla: {MBTILES_PATH}")
    print(f"🚀 Otwórz w przeglądarce: http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
