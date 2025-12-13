FROM python:3.11-slim

WORKDIR /app

# Instalacja zależności systemowych
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Kopiowanie i instalacja Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Kopiowanie kodu źródłowego
COPY . .

# Tworzenie katalogów
RUN mkdir -p /app/KMZ /app/cache /app/logs /app/data

# Zmienna środowiskowa dla unbuffered output
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Domyślne uruchomienie scheduler.py
CMD ["python", "-u", "scheduler.py"]
