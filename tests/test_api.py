import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def test_health_check_endpoint():
    response = client.get("/api/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "geospatial_backend" in data


def test_upload_and_get_kml():
    kml_path = SAMPLE_DIR / "sample_survey.kml"
    assert kml_path.exists()

    with open(kml_path, "rb") as f:
        response = client.post(
            "/api/files/",
            files={"file": ("sample_survey.kml", f, "application/vnd.google-earth.kml+xml")}
        )

    assert response.status_code == 201
    file_info = response.json()
    assert file_info["filename"] == "sample_survey.kml"
    assert file_info["status"] == "COMPLETED"
    assert file_info["feature_count"] >= 5
    file_id = file_info["id"]

    # Test GET /api/files/{id}/
    info_resp = client.get(f"/api/files/{file_id}/")
    assert info_resp.status_code == 200
    assert info_resp.json()["id"] == file_id

    # Test GET /api/files/{id}/measurements/
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    meas_data = meas_resp.json()
    assert meas_data["file_id"] == file_id
    assert meas_data["total_features"] == file_info["feature_count"]
    assert "summary" in meas_data
    assert meas_data["summary"]["polygon_count"] >= 2
    assert meas_data["summary"]["linestring_count"] >= 2
    assert meas_data["summary"]["point_count"] >= 2
    assert meas_data["summary"]["total_area_sq_meters"] > 0
    assert meas_data["summary"]["total_length_meters"] > 0

    # Check that features have measurements and UTM projected_crs
    features = meas_data["features"]
    poly_feat = next(f for f in features if f["geometry_type"] == "Polygon")
    assert poly_feat["measurement_type"] == "area"
    assert poly_feat["value"] > 0
    assert "EPSG:32618" in poly_feat["projected_crs"]

    point_feat = next(f for f in features if f["geometry_type"] == "Point")
    assert point_feat["status"] == "skipped_point"
    assert point_feat["value"] is None

    # Test GET /api/files/{id}/features/ (GeoJSON)
    geojson_resp = client.get(f"/api/files/{file_id}/features/")
    assert geojson_resp.status_code == 200
    geojson_data = geojson_resp.json()
    assert geojson_data["type"] == "FeatureCollection"
    assert len(geojson_data["features"]) == file_info["feature_count"]


def test_upload_and_get_shapefile_zip():
    zip_path = SAMPLE_DIR / "sample_parcels_shapefile.zip"
    assert zip_path.exists()

    with open(zip_path, "rb") as f:
        response = client.post(
            "/api/files/",
            files={"file": ("sample_parcels_shapefile.zip", f, "application/zip")}
        )

    assert response.status_code == 201
    file_info = response.json()
    assert file_info["filename"] == "sample_parcels_shapefile.zip"
    assert file_info["file_type"] == "shapefile"
    assert file_info["status"] == "COMPLETED"
    assert file_info["feature_count"] == 2

    file_id = file_info["id"]

    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    meas_data = meas_resp.json()
    assert meas_data["summary"]["polygon_count"] == 2
    assert meas_data["summary"]["total_area_sq_meters"] > 0


def test_list_files():
    list_resp = client.get("/api/files/")
    assert list_resp.status_code == 200
    files = list_resp.json()
    assert isinstance(files, list)
    assert len(files) >= 1


def test_delete_file():
    # Upload temporary file to delete
    kml_path = SAMPLE_DIR / "sample_survey.kml"
    with open(kml_path, "rb") as f:
        resp = client.post("/api/files/", files={"file": ("to_delete.kml", f, "application/vnd.google-earth.kml+xml")})
    file_id = resp.json()["id"]

    del_resp = client.delete(f"/api/files/{file_id}/")
    assert del_resp.status_code == 200

    # Ensure 404 on subsequent get
    get_resp = client.get(f"/api/files/{file_id}/")
    assert get_resp.status_code == 404


def test_invalid_extension_upload():
    response = client.post(
        "/api/files/",
        files={"file": ("test.pdf", b"fake pdf data", "application/pdf")}
    )
    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]
