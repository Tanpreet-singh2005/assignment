import pytest
import tempfile
import zipfile
from pathlib import Path
from app.core.parsers import GeospatialFileParser, GeospatialParserError

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def test_parse_sample_kml():
    kml_path = SAMPLE_DIR / "sample_survey.kml"
    assert kml_path.exists(), "Sample KML should exist"

    features, crs_str, geom_summary = GeospatialFileParser.parse_file(kml_path, "sample_survey.kml")

    assert len(features) >= 5
    assert "EPSG:4326" in crs_str
    assert "Polygon" in geom_summary
    assert "LineString" in geom_summary
    assert "Point" in geom_summary


def test_parse_sample_shapefile_zip():
    zip_path = SAMPLE_DIR / "sample_parcels_shapefile.zip"
    assert zip_path.exists(), "Sample Shapefile zip should exist"

    features, crs_str, geom_summary = GeospatialFileParser.parse_file(zip_path, "sample_parcels_shapefile.zip")

    assert len(features) == 2
    assert "Polygon" in geom_summary
    assert geom_summary["Polygon"] == 2


def test_invalid_zip_without_shp():
    with tempfile.NamedTemporaryFile("wb", suffix=".zip", delete=False) as f:
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("notes.txt", "No shapefile here")
        dummy_zip = Path(f.name)

    try:
        with pytest.raises(GeospatialParserError, match="No .shp file found"):
            GeospatialFileParser.parse_file(dummy_zip, "corrupt.zip")
    finally:
        dummy_zip.unlink(missing_ok=True)
