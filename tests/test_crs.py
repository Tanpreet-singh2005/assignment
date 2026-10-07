import pytest
from pyproj import CRS
from shapely.geometry import Polygon, LineString, Point
from app.core.crs import CRSService


def test_utm_epsg_determination():
    # New York City (-73.97, 40.78) -> Zone 18 North -> EPSG:32618
    epsg_ny = CRSService.get_utm_epsg_for_coordinates(-73.97, 40.78)
    assert epsg_ny == 32618

    # New Delhi (77.20, 28.61) -> Zone 43 North -> EPSG:32643
    epsg_delhi = CRSService.get_utm_epsg_for_coordinates(77.20, 28.61)
    assert epsg_delhi == 32643

    # Sydney (-151.20, -33.86) -> Zone 56 South -> EPSG:32756
    epsg_sydney = CRSService.get_utm_epsg_for_coordinates(151.20, -33.86)
    assert epsg_sydney == 32756

    # Extreme Arctic (> 84°N) -> UPS North EPSG:32661
    epsg_arctic = CRSService.get_utm_epsg_for_coordinates(0.0, 85.0)
    assert epsg_arctic == 32661

    # Extreme Antarctic (< -80°S) -> UPS South EPSG:32761
    epsg_antarctic = CRSService.get_utm_epsg_for_coordinates(0.0, -85.0)
    assert epsg_antarctic == 32761


def test_geometry_reprojection():
    # Polygon around Delhi in EPSG:4326
    poly = Polygon([(77.20, 28.60), (77.21, 28.60), (77.21, 28.61), (77.20, 28.61), (77.20, 28.60)])
    src_crs = CRS.from_epsg(4326)

    target_crs, crs_name = CRSService.determine_projected_crs(poly, src_crs)
    assert crs_name == "EPSG:32643"
    assert target_crs.is_projected

    projected_geom = CRSService.reproject_geometry(poly, src_crs, target_crs)
    assert projected_geom.area > 0.0
    # ~0.01 deg is ~1 km, so area is on order of ~1,000,000 m² (1 km²)
    assert 500_000 < projected_geom.area < 2_000_000
