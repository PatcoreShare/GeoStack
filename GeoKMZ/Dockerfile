FROM --platform=linux/amd64 python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y \
    gdal-bin libgdal-dev libproj-dev libspatialindex-dev gcc g++ pkg-config \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY . .
# ✅ config.json już jest w /app/config.json
RUN mkdir -p KMZ OSM_Data/{geojson_temp,overpass_cache} logs layers && chmod +x *.py
ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "scheduler.py"]