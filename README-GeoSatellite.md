# GeoSatelita - Geoportal Downloader & Scheduler

Kompletne narzędzie w Pythonie do **automatycznego pobierania** polskich ortofotomap z Geoportal.gov.pl w formacie **MBTiles**. Teraz z **Dockerem** i **schedulerem** – cykliczne aktualizacje map co X sekund/dni.

***

## 📋 Spis treści
1. [Szybki Start z Dockerem](#szybki-start-z-dockerm)
2. [Konfiguracja](#konfiguracja)
3. [Ręczne uruchamianie](#ręczne-uruchamianie)
4. [Podgląd mapy](#podgląd-mapy)
5. [Struktura plików](#struktura-plików)
6. [Rozwiązywanie problemów](#rozwiązywanie-problemów)

***

## 🚀 Szybki Start z Dockerem

### 1. Pobierz projekt
```bash
git clone <repo> && cd GeoSatelita
```

### 2. Skonfiguruj `.env` (opcjonalnie)
```env
# Cała Polska
LAYER=ORTO_STD
BBOX_W=14.0
BBOX_S=48.5
BBOX_E=24.5
BBOX_N=55.0
MIN_ZOOM=1
MAX_ZOOM=16

INTERVAL_SECONDS=3600  # co 1 godzinę (86400 = 1 dzień)
```

### 3. Uruchom automatyczne pobieranie
```bash
docker compose up -d --build
```

**Co się dzieje:**
- Scheduler uruchamia się co `INTERVAL_SECONDS`
- Pliki MBTiles lądują w `./data/` z timestampem: `orto_std_z1-16_2025-12-13-20-45.mbtiles`
- Automatyczny restart przy błędach

### 4. Logi na żywo
```bash
docker compose logs -f geosatelita
```

### 5. Zatrzymanie
```bash
docker compose down
```

***

## 🖥 Ręczne uruchamianie (bez Dockera)

### Wymagania
```bash
python3 -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Pobieranie ręczne
```bash
# Testowy obszar
python main.py --layer ORTO_STD -b 20.70 52.42 20.74 52.45 --min-zoom 1 --max-zoom 11

# Pełna mapa Polski (UWAGA: DUŻO danych!)
python main.py --layer ORTO_STD -b 14.0 48.5 24.5 55.0 --min-zoom 1 --max-zoom 16
```

***

## 🌍 Podgląd mapy do szybkich testów (`mbview.py`) 

**Inteligentny viewer automatycznie wybiera najnowszy plik MBTiles!**

### Uruchomienie:
```bash
# Automatycznie otworzy NAJNOWSZY plik z data/
python mbview.py

# Lub konkretny plik
python mbview.py data/orto_std_z1-11_2025-12-13-20-45.mbtiles
```

Otwórz: **http://127.0.0.1:8000**

### Funkcje viewer'a:
- **🟢 Zielony licznik** = dane dostępne dla aktualnego zoomu
- **🔴 Czerwony licznik** = brak danych (za bardzo przybliżyłeś/oddaliłeś)
- **Automatyczne centrowanie** na podstawie `bounds` z metadanych MBTiles
- **Blokada zoomu** poza zakresem danych
- **Auto-wykrywanie PNG/JPG** kafelków

***


## 📂 Struktura plików

```
GeoSatelita/
├── data/                    # ← TUTAJ lądują MBTiles z timestampem
│   ├── orto_std_z1-11_2025-12-13-20-45.mbtiles
│   └── orto_std_z1-16_2025-12-14-01-30.mbtiles
├── src/                     # Kod źródłowy
│   ├── downloader.py
│   ├── storage.py
│   └── utils.py
├── main.py                  # CLI pobieranie
├── scheduler.py             # ← Scheduler cykliczny
├── mbview.py                # Podgląd mapy
├── Dockerfile               # Docker
├── docker-compose.yml       # Docker Compose
├── .env.example             # Szablon konfiguracji
└── requirements.txt
```

