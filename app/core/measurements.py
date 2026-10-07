import math
from typing import Any, Dict, Optional, Tuple
from pyproj import CRS, Geod
from shapely.geometry import (
    GeometryCollection,
    LinearRing,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry

from app.core.crs import CRSService
from app.models.schemas import FeatureMeasurement

# Standard WGS84 Geodesic calculator
_geod = Geod(ellps="WGS84")


class MeasurementService:
    """Service to compute accurate spatial measurements for various geometry types."""

    @classmethod
    def calculate_feature_measurement(
        cls,
        feature_id: Any,
        geometry: Optional[BaseGeometry],
        source_crs: CRS,
        properties: Optional[Dict[str, Any]] = None,
        include_geometry_geojson: bool = False
    ) -> FeatureMeasurement:
        """
        Compute measurements for a given geometry, handling CRS reprojection,
        supported/unsupported types, points, and gracefully avoiding crashes.
        """
        properties = properties or {}
        geo_dict = geometry.__geo_interface__ if (geometry and include_geometry_geojson) else None

        if geometry is None or geometry.is_empty:
            return FeatureMeasurement(
                feature_id=feature_id,
                geometry_type="None",
                measurement_type="none",
                value=None,
                unit=None,
                formatted_value="N/A (Empty Geometry)",
                projected_crs=None,
                status="empty_geometry",
                message="Feature has null or empty geometry",
                properties=properties,
                geometry=geo_dict
            )

        geom_type = geometry.geom_type

        # 1. Point and MultiPoint: Explicitly no measurement required
        if geom_type in ("Point", "MultiPoint"):
            return FeatureMeasurement(
                feature_id=feature_id,
                geometry_type=geom_type,
                measurement_type="none",
                value=None,
                unit=None,
                formatted_value="N/A (Point feature)",
                projected_crs=None,
                status="skipped_point",
                message="Measurement not required for Point geometries.",
                properties=properties,
                geometry=geo_dict
            )

        # 2. Polygons & MultiPolygons: Calculate Area
        if geom_type in ("Polygon", "MultiPolygon"):
            try:
                target_crs, projected_crs_name = CRSService.determine_projected_crs(geometry, source_crs)
                projected_geom = CRSService.reproject_geometry(geometry, source_crs, target_crs)

                area_m2 = float(projected_geom.area)
                perimeter_m = float(projected_geom.length)

                # Ellipsoidal geodesic area calculation for comparison
                geodesic_area_m2 = None
                try:
                    wgs84 = CRS.from_epsg(4326)
                    geom_wgs84 = CRSService.reproject_geometry(geometry, source_crs, wgs84)
                    if geom_wgs84.geom_type == "Polygon":
                        geod_area, _ = _geod.geometry_area_perimeter(geom_wgs84)
                        geodesic_area_m2 = abs(geod_area)
                    elif geom_wgs84.geom_type == "MultiPolygon":
                        geodesic_area_m2 = sum(abs(_geod.geometry_area_perimeter(p)[0]) for p in geom_wgs84.geoms)
                except Exception:
                    pass

                hectares = area_m2 / 10000.0
                sq_km = area_m2 / 1000000.0
                acres = area_m2 * 0.000247105

                formatted = f"{area_m2:,.2f} m² ({hectares:,.4f} ha)"

                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type="area",
                    value=round(area_m2, 4),
                    unit="square_meters",
                    formatted_value=formatted,
                    projected_crs=projected_crs_name,
                    additional_units={
                        "hectares": round(hectares, 4),
                        "square_kilometers": round(sq_km, 6),
                        "acres": round(acres, 4),
                        "perimeter_meters": round(perimeter_m, 2)
                    },
                    perimeter_or_length_meters=round(perimeter_m, 2),
                    geodesic_value=round(geodesic_area_m2, 4) if geodesic_area_m2 is not None else None,
                    status="success",
                    properties=properties,
                    geometry=geo_dict
                )
            except Exception as e:
                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type="area",
                    value=None,
                    unit="square_meters",
                    formatted_value="Calculation Error",
                    status="error",
                    message=f"Failed to calculate polygon area: {str(e)}",
                    properties=properties,
                    geometry=geo_dict
                )

        # 3. LineStrings, MultiLineStrings, LinearRings: Calculate Length
        if geom_type in ("LineString", "MultiLineString", "LinearRing"):
            try:
                target_crs, projected_crs_name = CRSService.determine_projected_crs(geometry, source_crs)
                projected_geom = CRSService.reproject_geometry(geometry, source_crs, target_crs)

                length_m = float(projected_geom.length)
                km = length_m / 1000.0
                miles = length_m * 0.000621371

                # Ellipsoidal geodesic length calculation
                geodesic_length_m = None
                try:
                    wgs84 = CRS.from_epsg(4326)
                    geom_wgs84 = CRSService.reproject_geometry(geometry, source_crs, wgs84)
                    geodesic_length_m = _geod.geometry_length(geom_wgs84)
                except Exception:
                    pass

                formatted = f"{length_m:,.2f} m ({km:,.3f} km)"

                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type="length",
                    value=round(length_m, 4),
                    unit="meters",
                    formatted_value=formatted,
                    projected_crs=projected_crs_name,
                    additional_units={
                        "kilometers": round(km, 4),
                        "miles": round(miles, 4)
                    },
                    perimeter_or_length_meters=round(length_m, 2),
                    geodesic_value=round(geodesic_length_m, 4) if geodesic_length_m is not None else None,
                    status="success",
                    properties=properties,
                    geometry=geo_dict
                )
            except Exception as e:
                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type="length",
                    value=None,
                    unit="meters",
                    formatted_value="Calculation Error",
                    status="error",
                    message=f"Failed to calculate line length: {str(e)}",
                    properties=properties,
                    geometry=geo_dict
                )

        # 4. GeometryCollection
        if geom_type == "GeometryCollection":
            try:
                target_crs, projected_crs_name = CRSService.determine_projected_crs(geometry, source_crs)
                projected_geom = CRSService.reproject_geometry(geometry, source_crs, target_crs)

                total_area = sum(g.area for g in projected_geom.geoms if g.geom_type in ("Polygon", "MultiPolygon"))
                total_len = sum(g.length for g in projected_geom.geoms if g.geom_type in ("LineString", "MultiLineString", "LinearRing"))

                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type="collection",
                    value=round(total_area or total_len, 4),
                    unit="square_meters" if total_area > 0 else "meters",
                    formatted_value=f"Area: {total_area:,.2f} m², Length: {total_len:,.2f} m",
                    projected_crs=projected_crs_name,
                    additional_units={
                        "area_sq_meters": round(total_area, 2),
                        "length_meters": round(total_len, 2)
                    },
                    status="success",
                    properties=properties,
                    geometry=geo_dict
                )
            except Exception as e:
                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type="collection",
                    value=None,
                    unit=None,
                    formatted_value="Collection Error",
                    status="error",
                    message=f"Error measuring GeometryCollection: {str(e)}",
                    properties=properties,
                    geometry=geo_dict
                )

        # 5. Unsupported geometry types (graceful handling rather than crashing)
        return FeatureMeasurement(
            feature_id=feature_id,
            geometry_type=geom_type,
            measurement_type="unsupported",
            value=None,
            unit=None,
            formatted_value=f"Unsupported ({geom_type})",
            projected_crs=None,
            status="unsupported_geometry",
            message=f"Geometry type '{geom_type}' is not currently supported for measurement calculation.",
            properties=properties,
            geometry=geo_dict
        )
