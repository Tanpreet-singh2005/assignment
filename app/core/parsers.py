import os
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import geopandas as gpd
from pyproj import CRS
from shapely.geometry import shape, Point, LineString, Polygon, MultiPolygon, MultiLineString, MultiPoint, GeometryCollection
from shapely.geometry.base import BaseGeometry

import pandas as pd
from app.config import DEFAULT_CRS
from app.core.crs import CRSService


def sanitize_attribute_value(val: Any) -> Any:
    """Sanitize pandas/numpy types for JSON serialization."""
    if val is None or pd.isna(val):
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if hasattr(val, "item"):
        try:
            return val.item()
        except Exception:
            pass
    return val


class GeospatialParserError(Exception):
    """Custom exception raised when file extraction or parsing fails."""
    pass


class GeospatialFileParser:
    """Parser to handle uploaded Shapefile (.zip) and KML (.kml) geospatial files."""

    @classmethod
    def parse_file(cls, file_path: Path, filename: str) -> Tuple[List[Dict[str, Any]], str, Dict[str, int]]:
        """
        Entry point to parse either a Shapefile (.zip) or a KML file.
        Returns:
            features: List of dictionaries with feature_id, geometry, geometry_type, properties, source_crs
            crs_str: The detected or assigned CRS string (e.g., 'EPSG:4326')
            geometry_summary: Dict mapping geometry types to their counts
        """
        lower_name = filename.lower()
        if lower_name.endswith(".zip"):
            return cls.parse_shapefile_zip(file_path)
        elif lower_name.endswith(".kml"):
            return cls.parse_kml_file(file_path)
        else:
            raise GeospatialParserError(f"Unsupported file format: {filename}. Allowed formats are .zip and .kml")

    @classmethod
    def parse_shapefile_zip(cls, zip_path: Path) -> Tuple[List[Dict[str, Any]], str, Dict[str, int]]:
        """
        Extract and parse a Shapefile contained in a .zip archive.
        Safely unpacks to a temporary directory with zip slip protection.
        """
        temp_dir = tempfile.mkdtemp(prefix="shp_extract_")
        try:
            # 1. Unzip safely
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    target_path = Path(temp_dir) / member.filename
                    # Path traversal protection
                    if not target_path.resolve().is_relative_to(Path(temp_dir).resolve()):
                        raise GeospatialParserError("Zip archive contains invalid paths (possible zip-slip).")
                zf.extractall(temp_dir)

            # 2. Locate .shp file
            shp_files = list(Path(temp_dir).rglob("*.shp"))
            if not shp_files:
                raise GeospatialParserError("No .shp file found inside the uploaded .zip archive.")

            primary_shp = shp_files[0]

            # 3. Read with geopandas
            try:
                gdf = gpd.read_file(primary_shp)
            except Exception as e:
                raise GeospatialParserError(f"Failed to read shapefile: {str(e)}")

            if len(gdf) == 0:
                return [], DEFAULT_CRS, {}

            # Determine CRS
            crs_obj = gdf.crs
            if crs_obj is None:
                # Default to EPSG:4326 if .prj is missing
                source_crs = CRS.from_epsg(4326)
                crs_str = f"{DEFAULT_CRS} (assumed, .prj missing)"
            else:
                source_crs = CRSService.parse_crs(crs_obj)
                epsg = source_crs.to_epsg()
                crs_str = f"EPSG:{epsg}" if epsg else (source_crs.to_string() or DEFAULT_CRS)

            # 4. Extract features
            features = []
            geometry_summary = {}

            for idx, row in gdf.iterrows():
                geom: Optional[BaseGeometry] = row.geometry
                geom_type = geom.geom_type if geom is not None and not geom.is_empty else "None"
                geometry_summary[geom_type] = geometry_summary.get(geom_type, 0) + 1

                # Clean property dictionary (convert non-serializable objects)
                properties = {
                    str(col): sanitize_attribute_value(row[col])
                    for col in gdf.columns
                    if col != "geometry"
                }

                features.append({
                    "feature_id": idx,
                    "geometry": geom,
                    "geometry_type": geom_type,
                    "properties": properties,
                    "source_crs": source_crs,
                    "source_crs_str": crs_str
                })

            return features, crs_str, geometry_summary

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @classmethod
    def parse_kml_file(cls, kml_path: Path) -> Tuple[List[Dict[str, Any]], str, Dict[str, int]]:
        """
        Parse a KML (.kml) file.
        Attempts pyogrio/geopandas first; if empty or fails, falls back to direct XML parsing.
        """
        crs_str = "EPSG:4326"  # KML standard is strictly WGS84
        source_crs = CRS.from_epsg(4326)

        # Strategy A: Use GeoPandas with pyogrio
        try:
            gdf = gpd.read_file(kml_path, engine="pyogrio")
            if len(gdf) > 0:
                features = []
                geometry_summary = {}
                for idx, row in gdf.iterrows():
                    geom = row.geometry
                    geom_type = geom.geom_type if geom is not None and not geom.is_empty else "None"
                    geometry_summary[geom_type] = geometry_summary.get(geom_type, 0) + 1

                    properties = {
                        str(col): sanitize_attribute_value(row[col])
                        for col in gdf.columns
                        if col != "geometry"
                    }

                    features.append({
                        "feature_id": idx,
                        "geometry": geom,
                        "geometry_type": geom_type,
                        "properties": properties,
                        "source_crs": source_crs,
                        "source_crs_str": crs_str
                    })
                return features, crs_str, geometry_summary
        except Exception:
            # Fall back to Strategy B: Direct KML XML parsing
            pass

        # Strategy B: Robust XML Placemark parser for KML
        return cls._parse_kml_xml_fallback(kml_path, source_crs, crs_str)

    @classmethod
    def _parse_kml_xml_fallback(
        cls,
        kml_path: Path,
        source_crs: CRS,
        crs_str: str
    ) -> Tuple[List[Dict[str, Any]], str, Dict[str, int]]:
        """
        XML parser fallback for KML files with nested Placemarks or varied namespaces.
        """
        try:
            tree = ET.parse(kml_path)
            root = tree.getroot()
        except Exception as e:
            raise GeospatialParserError(f"Failed to parse KML XML document: {str(e)}")

        # Namespaces handling
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        placemarks = root.findall(f".//{ns}Placemark")
        features = []
        geometry_summary = {}

        for idx, placemark in enumerate(placemarks):
            # Extract basic metadata
            name_el = placemark.find(f"{ns}name")
            desc_el = placemark.find(f"{ns}description")
            name = name_el.text if name_el is not None else f"Feature_{idx}"
            desc = desc_el.text if desc_el is not None else ""

            properties = {"Name": name, "Description": desc}

            # ExtendedData
            ext_data = placemark.find(f"{ns}ExtendedData")
            if ext_data is not None:
                for data_el in ext_data.findall(f"{ns}Data"):
                    d_name = data_el.attrib.get("name")
                    d_val_el = data_el.find(f"{ns}value")
                    if d_name and d_val_el is not None:
                        properties[d_name] = d_val_el.text

            # Parse Geometry
            geom = cls._extract_kml_geometry(placemark, ns)
            geom_type = geom.geom_type if geom is not None and not geom.is_empty else "None"
            geometry_summary[geom_type] = geometry_summary.get(geom_type, 0) + 1

            features.append({
                "feature_id": idx,
                "geometry": geom,
                "geometry_type": geom_type,
                "properties": properties,
                "source_crs": source_crs,
                "source_crs_str": crs_str
            })

        return features, crs_str, geometry_summary

    @classmethod
    def _extract_kml_geometry(cls, placemark: ET.Element, ns: str) -> Optional[BaseGeometry]:
        """Extract a Shapely geometry from a KML Placemark element."""
        # 1. Polygon
        poly_el = placemark.find(f".//{ns}Polygon")
        if poly_el is not None:
            outer_ring = poly_el.find(f".//{ns}outerBoundaryIs//{ns}coordinates")
            if outer_ring is not None and outer_ring.text:
                coords = cls._parse_coord_string(outer_ring.text)
                if len(coords) >= 3:
                    inner_rings = []
                    for inner in poly_el.findall(f".//{ns}innerBoundaryIs//{ns}coordinates"):
                        if inner.text:
                            inner_coords = cls._parse_coord_string(inner.text)
                            if len(inner_coords) >= 3:
                                inner_rings.append(inner_coords)
                    return Polygon(coords, inner_rings)

        # 2. LineString
        line_el = placemark.find(f".//{ns}LineString")
        if line_el is not None:
            coord_el = line_el.find(f"{ns}coordinates")
            if coord_el is not None and coord_el.text:
                coords = cls._parse_coord_string(coord_el.text)
                if len(coords) >= 2:
                    return LineString(coords)

        # 3. Point
        point_el = placemark.find(f".//{ns}Point")
        if point_el is not None:
            coord_el = point_el.find(f"{ns}coordinates")
            if coord_el is not None and coord_el.text:
                coords = cls._parse_coord_string(coord_el.text)
                if coords:
                    return Point(coords[0])

        # 4. MultiGeometry
        multi_el = placemark.find(f".//{ns}MultiGeometry")
        if multi_el is not None:
            geoms = []
            for child in multi_el:
                child_geom = cls._extract_kml_geometry(child, ns)
                if child_geom:
                    geoms.append(child_geom)
            if geoms:
                return GeometryCollection(geoms)

        return None

    @staticmethod
    def _parse_coord_string(coord_str: str) -> List[Tuple[float, float]]:
        """Parse coordinate tuples from KML text format 'lon,lat,alt lon,lat,alt'."""
        points = []
        tokens = coord_str.strip().split()
        for token in tokens:
            parts = token.split(",")
            if len(parts) >= 2:
                try:
                    lon = float(parts[0].strip())
                    lat = float(parts[1].strip())
                    points.append((lon, lat))
                except ValueError:
                    continue
        return points
