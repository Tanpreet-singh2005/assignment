import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Application Settings
APP_NAME = "Geospatial File Measurement API"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = (
    "Production-ready FastAPI service for uploading Shapefile (.zip) and KML (.kml) files, "
    "parsing geospatial features, handling CRS reprojection, and calculating accurate geographic measurements."
)

# Allowed file extensions
ALLOWED_EXTENSIONS = {".zip", ".kml"}

# Maximum upload size in bytes (e.g., 50MB)
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024

# Default fallback CRS if file lacks spatial reference metadata
DEFAULT_CRS = "EPSG:4326"
