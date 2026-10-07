import math
from typing import Optional, Tuple
import numpy as np
import shapely
from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry


class CRSService:
    """Service to inspect, determine, and transform Coordinate Reference Systems (CRS)."""

    _transformer_cache = {}

    @classmethod
    def get_transformer(cls, source_crs: CRS, target_crs: CRS) -> Transformer:
        """Get or cache a pyproj Transformer between two CRS."""
        key = (source_crs.to_string(), target_crs.to_string())
        if key not in cls._transformer_cache:
            cls._transformer_cache[key] = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        return cls._transformer_cache[key]

    @staticmethod
    def parse_crs(crs_input: Optional[any]) -> CRS:
        """Parse CRS input from various formats (EPSG string, WKT, dict, or CRS object)."""
        if crs_input is None:
            return CRS.from_epsg(4326)
        if isinstance(crs_input, CRS):
            return crs_input
        try:
            return CRS.from_user_input(crs_input)
        except Exception:
            # Fallback to WGS84
            return CRS.from_epsg(4326)

    @staticmethod
    def get_utm_epsg_for_coordinates(longitude: float, latitude: float) -> int:
        """
        Determine the appropriate UTM EPSG code for a given longitude and latitude.
        - Longitudes -180 to 180 map to UTM zones 1 to 60.
        - Latitudes >= 0 use EPSG:32601 - 32660 (WGS 84 / UTM Northern Hemisphere).
        - Latitudes < 0 use EPSG:32701 - 32760 (WGS 84 / UTM Southern Hemisphere).
        - Polar regions (>84°N or <-80°S) use UPS (EPSG:32661 / 32761).
        """
        # Handle polar extremes with Universal Polar Stereographic (UPS)
        if latitude > 84.0:
            return 32661  # UPS North
        if latitude < -80.0:
            return 32761  # UPS South

        # Normalize longitude between -180 and 180
        norm_lon = ((longitude + 180.0) % 360.0) - 180.0
        zone = int(math.floor((norm_lon + 180.0) / 6.0)) + 1
        zone = max(1, min(60, zone))

        if latitude >= 0:
            return 32600 + zone
        else:
            return 32700 + zone

    @classmethod
    def determine_projected_crs(cls, geometry: BaseGeometry, source_crs: CRS) -> Tuple[CRS, str]:
        """
        Determine an optimal projected metric CRS for a geometry.
        If the geometry is in geographic degrees (like EPSG:4326) or Web Mercator (EPSG:3857,
        which has severe area distortion away from the equator), find its centroid in WGS84
        and select the best UTM zone projection.
        """
        # Check if already a localized projected CRS (e.g. local UTM or State Plane)
        # Web Mercator EPSG:3857 is projected, but distorts scale by 1/cos(lat), so reproject to UTM
        is_web_mercator = False
        try:
            auth = source_crs.to_authority()
            if auth and auth[0] == "EPSG" and auth[1] == "3857":
                is_web_mercator = True
        except Exception:
            pass

        if source_crs.is_projected and not is_web_mercator:
            # Check unit of measurement
            unit_name = source_crs.axis_info[0].unit_name.lower() if source_crs.axis_info else "metre"
            if "metre" in unit_name or "meter" in unit_name:
                crs_str = f"EPSG:{source_crs.to_epsg()}" if source_crs.to_epsg() else source_crs.name
                return source_crs, crs_str

        # Otherwise, project to appropriate UTM zone based on geometry centroid
        wgs84 = CRS.from_epsg(4326)

        # Get centroid coordinates in WGS84
        if source_crs.is_geographic:
            centroid = geometry.centroid
            lon, lat = centroid.x, centroid.y
        else:
            # Transform centroid to WGS84 first
            to_wgs84 = cls.get_transformer(source_crs, wgs84)
            cx, cy = geometry.centroid.x, geometry.centroid.y
            lon, lat = to_wgs84.transform(cx, cy)

        target_epsg = cls.get_utm_epsg_for_coordinates(lon, lat)
        target_crs = CRS.from_epsg(target_epsg)
        return target_crs, f"EPSG:{target_epsg}"

    @classmethod
    def reproject_geometry(
        cls,
        geometry: BaseGeometry,
        source_crs: CRS,
        target_crs: CRS
    ) -> BaseGeometry:
        """
        Reproject a Shapely geometry from source_crs to target_crs using Shapely 2.0 vectorized transform.
        """
        if source_crs == target_crs:
            return geometry

        transformer = cls.get_transformer(source_crs, target_crs)

        def _transform_coords(coords):
            x, y = coords[:, 0], coords[:, 1]
            xt, yt = transformer.transform(x, y)
            return np.column_stack((xt, yt))

        return shapely.transform(geometry, _transform_coords)
