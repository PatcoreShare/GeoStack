import mercantile

def get_tiles_list(bbox, zoom):
    return list(mercantile.tiles(*bbox, zooms=[zoom]))

def flip_y(z, y):
    """Odwraca Y dla formatu MBTiles (XYZ -> TMS)."""
    return (2**z - 1) - y

def estimate_size(tile_count):
    # Zakładamy 20KB na kafelek JPG (bezpieczny margines)
    return f"{(tile_count * 20) / 1024:.2f} MB"
