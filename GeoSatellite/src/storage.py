import sqlite3
from pathlib import Path

class MBTilesStorage:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.conn = None
        self.cursor = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.filepath)
        self.cursor = self.conn.cursor()
        self._init_schema()
        # Optymalizacja SQLite dla szybkiego zapisu
        self.cursor.execute("PRAGMA synchronous=OFF")
        self.cursor.execute("PRAGMA journal_mode=MEMORY")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.commit()
            self.conn.close()

    def _init_schema(self):
        self.cursor.execute("CREATE TABLE IF NOT EXISTS metadata (name text, value text)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob)")
        self.cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS tile_index on tiles (zoom_level, tile_column, tile_row)")

    def save_metadata(self, name, description, bounds_str, fmt="jpg"): # Wymuszamy jpg
        meta = [
            ('name', name),
            ('type', 'overlay'),
            ('version', '1.2'),
            ('description', description),
            ('format', fmt),
            ('bounds', bounds_str)
        ]
        self.cursor.executemany("INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)", meta)

    def save_tile(self, z, x, y_tms, data):
        """
        Zapisuje kafelek.
        UWAGA: Oczekuje już przeliczonego Y (TMS)!
        """
        try:
            self.cursor.execute(
                "INSERT OR IGNORE INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
                (z, x, y_tms, data)
            )
        except sqlite3.Error as e:
            print(f"Błąd SQL przy kafelku {z}/{x}/{y_tms}: {e}")
            
    def commit(self):
        self.conn.commit()
