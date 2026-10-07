import pytest
from pyproj import CRS
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point, MultiPoint
from app.core.measurements import MeasurementService


def test_polygon_measurement():
    src_crs = CRS.from_epsg(4326)
    # 0.01 deg square near New Delhi
    poly = Polygon([(77.20, 28.60), (77.21, 28.60), (77.21, 28.61), (77.20, 28.61), (77.20, 28.60)])

    res = MeasurementService.calculate_feature_measurement(
        feature_id=1,
        geometry=poly,
        source_crs=src_crs,
        properties={"name": "Test Parcel"}
    )

    assert res.feature_id == 1
    assert res.geometry_type == "Polygon"
    assert res.measurement_type == "area"
    assert res.unit == "square_meters"
    assert res.status == "success"
    assert res.value is not None
    assert res.value > 500_000  # Should be in metric square meters, NOT tiny degree square (0.0001)
    assert res.projected_crs == "EPSG:32643"
    assert "hectares" in res.additional_units
    assert res.additional_units["hectares"] > 50


def test_linestring_measurement():
    src_crs = CRS.from_epsg(4326)
    # Line of ~0.02 deg length (~2 km)
    line = LineString([(77.20, 28.60), (77.22, 28.60)])

    res = MeasurementService.calculate_feature_measurement(
        feature_id="line_1",
        geometry=line,
        source_crs=src_crs
    )

    assert res.feature_id == "line_1"
    assert res.geometry_type == "LineString"
    assert res.measurement_type == "length"
    assert res.unit == "meters"
    assert res.status == "success"
    assert res.value is not None
    # ~0.02 deg longitude at 28.6N is approx 1,950 meters
    assert 1800 < res.value < 2200
    assert "kilometers" in res.additional_units


def test_point_handling_no_crash():
    src_crs = CRS.from_epsg(4326)
    pt = Point(77.20, 28.60)

    res = MeasurementService.calculate_feature_measurement(
        feature_id=42,
        geometry=pt,
        source_crs=src_crs,
        properties={"station": "Alpha"}
    )

    assert res.feature_id == 42
    assert res.geometry_type == "Point"
    assert res.measurement_type == "none"
    assert res.value is None
    assert res.status == "skipped_point"
    assert "not required" in res.message.lower()


def test_unsupported_or_empty_geometry_handling():
    src_crs = CRS.from_epsg(4326)

    # Empty geometry
    empty_poly = Polygon()
    res_empty = MeasurementService.calculate_feature_measurement(
        feature_id=99,
        geometry=empty_poly,
        source_crs=src_crs
    )
    assert res_empty.status == "empty_geometry"
    assert res_empty.value is None


def test_multipolygon_measurement():
    src_crs = CRS.from_epsg(4326)
    p1 = Polygon([(77.20, 28.60), (77.21, 28.60), (77.21, 28.61), (77.20, 28.61), (77.20, 28.60)])
    p2 = Polygon([(77.22, 28.60), (77.23, 28.60), (77.23, 28.61), (77.22, 28.61), (77.22, 28.60)])
    mp = MultiPolygon([p1, p2])

    res = MeasurementService.calculate_feature_measurement(
        feature_id="mp_1",
        geometry=mp,
        source_crs=src_crs
    )
    assert res.geometry_type == "MultiPolygon"
    assert res.measurement_type == "area"
    assert res.value > 1_000_000
    assert res.status == "success"


def test_multilinestring_measurement():
    src_crs = CRS.from_epsg(4326)
    l1 = LineString([(77.20, 28.60), (77.21, 28.60)])
    l2 = LineString([(77.21, 28.60), (77.22, 28.60)])
    mls = MultiLineString([l1, l2])

    res = MeasurementService.calculate_feature_measurement(
        feature_id="mls_1",
        geometry=mls,
        source_crs=src_crs
    )
    assert res.geometry_type == "MultiLineString"
    assert res.measurement_type == "length"
    assert res.value > 1800
    assert res.status == "success"
