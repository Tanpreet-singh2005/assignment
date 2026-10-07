import os
import zipfile
import tempfile
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Polygon, LineString, Point

SAMPLES_DIR = Path(__file__).resolve().parent
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def create_sample_kml():
    """Create a realistic sample KML file with Polygons, LineStrings, and Points."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Urban Infrastructure Survey</name>
    <description>Sample surveying dataset containing agricultural parcels, roadways, and control points.</description>
    
    <!-- Polygons -->
    <Placemark>
      <name>Central Park Sector A</name>
      <description>Public recreation zone with grass lawn</description>
      <ExtendedData>
        <Data name="zone_type"><value>Recreation</value></Data>
        <Data name="inspector"><value>Sarah Jenkins</value></Data>
      </ExtendedData>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              -73.973,40.764,0
              -73.981,40.768,0
              -73.971,40.782,0
              -73.963,40.778,0
              -73.973,40.764,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>

    <Placemark>
      <name>Botanical Reservoir Quad</name>
      <description>Water catchment perimeter</description>
      <ExtendedData>
        <Data name="zone_type"><value>Waterbody</value></Data>
      </ExtendedData>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              -73.965,40.785,0
              -73.968,40.787,0
              -73.962,40.793,0
              -73.959,40.791,0
              -73.965,40.785,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>

    <!-- LineStrings -->
    <Placemark>
      <name>East River Greenway Path</name>
      <description>Paved pedestrian and bike transit trail</description>
      <ExtendedData>
        <Data name="route_id"><value>RT-109</value></Data>
        <Data name="surface"><value>Asphalt</value></Data>
      </ExtendedData>
      <LineString>
        <coordinates>
          -73.960,40.755,0
          -73.964,40.762,0
          -73.967,40.771,0
          -73.972,40.780,0
        </coordinates>
      </LineString>
    </Placemark>

    <Placemark>
      <name>Main Water Main Conduit</name>
      <description>Subsurface pipeline</description>
      <ExtendedData>
        <Data name="diameter_mm"><value>600</value></Data>
      </ExtendedData>
      <LineString>
        <coordinates>
          -73.985,40.750,0
          -73.978,40.758,0
          -73.970,40.765,0
        </coordinates>
      </LineString>
    </Placemark>

    <!-- Points -->
    <Placemark>
      <name>Geodetic Bench Mark #41</name>
      <description>High precision GPS calibration monument</description>
      <ExtendedData>
        <Data name="elevation_m"><value>24.5</value></Data>
      </ExtendedData>
      <Point>
        <coordinates>-73.970,40.770,0</coordinates>
      </Point>
    </Placemark>

    <Placemark>
      <name>Observation Tower Summit</name>
      <description>Weather monitoring station</description>
      <Point>
        <coordinates>-73.965,40.780,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""
    kml_file = SAMPLES_DIR / "sample_survey.kml"
    with open(kml_file, "w", encoding="utf-8") as f:
        f.write(kml_content)
    print(f"Created KML sample: {kml_file}")


def create_sample_shapefile_zip():
    """Create a sample ESRI Shapefile zipped archive (.zip) with Polygons and LineStrings."""
    # Data 1: Polygons
    poly_data = {
        "name": ["Parc Central", "Harbor Terminal"],
        "category": ["Zone-A", "Commercial"],
        "geometry": [
            Polygon([(77.20, 28.60), (77.22, 28.60), (77.22, 28.62), (77.20, 28.62), (77.20, 28.60)]),
            Polygon([(77.25, 28.65), (77.28, 28.65), (77.28, 28.67), (77.25, 28.67), (77.25, 28.65)])
        ]
    }
    gdf_poly = gpd.GeoDataFrame(poly_data, crs="EPSG:4326")

    # Data 2: Lines
    line_data = {
        "name": ["Highway corridor 1", "River canal 2"],
        "speed_kmh": [80, 0],
        "geometry": [
            LineString([(77.20, 28.60), (77.25, 28.63), (77.30, 28.68)]),
            LineString([(77.22, 28.58), (77.24, 28.62), (77.26, 28.66)])
        ]
    }
    gdf_lines = gpd.GeoDataFrame(line_data, crs="EPSG:4326")

    temp_dir = tempfile.mkdtemp(prefix="shp_gen_")
    try:
        shp_path = Path(temp_dir) / "land_parcels.shp"
        gdf_poly.to_file(shp_path)

        zip_target = SAMPLES_DIR / "sample_parcels_shapefile.zip"
        with zipfile.ZipFile(zip_target, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in Path(temp_dir).glob("land_parcels.*"):
                zf.write(f, arcname=f.name)
        print(f"Created Shapefile sample zip: {zip_target}")

        # Also create a lines shapefile zip
        line_shp_path = Path(temp_dir) / "corridors.shp"
        gdf_lines.to_file(line_shp_path)
        zip_lines = SAMPLES_DIR / "sample_lines_shapefile.zip"
        with zipfile.ZipFile(zip_lines, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in Path(temp_dir).glob("corridors.*"):
                zf.write(f, arcname=f.name)
        print(f"Created Lines Shapefile sample zip: {zip_lines}")

    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    create_sample_kml()
    create_sample_shapefile_zip()
