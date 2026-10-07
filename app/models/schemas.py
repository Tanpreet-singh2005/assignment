from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class GeometrySummary(BaseModel):
    """Summary counts of geometry types found in the file."""
    polygons: int = 0
    linestrings: int = 0
    points: int = 0
    multipolygons: int = 0
    multilinestrings: int = 0
    multipoints: int = 0
    geometry_collections: int = 0
    other: int = 0


class FileInfoResponse(BaseModel):
    """Information and metadata about an uploaded geospatial file."""
    id: str = Field(..., description="Unique file identifier (UUID)")
    filename: str = Field(..., description="Original uploaded filename")
    file_type: str = Field(..., description="Detected file type ('shapefile' or 'kml')")
    file_size_bytes: int = Field(..., description="File size in bytes")
    feature_count: int = Field(..., description="Total count of features contained")
    crs: str = Field(..., description="Detected or assigned Coordinate Reference System")
    status: str = Field(..., description="Processing status: PENDING, COMPLETED, or FAILED")
    geometry_summary: Dict[str, int] = Field(
        default_factory=dict,
        description="Distribution of geometry types present in the dataset"
    )
    created_at: datetime = Field(..., description="Timestamp of upload")
    error_message: Optional[str] = Field(None, description="Error details if processing failed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "7b8f9e20-1a2b-4c3d-9e8f-0123456789ab",
                "filename": "survey.kml",
                "file_type": "kml",
                "file_size_bytes": 14250,
                "feature_count": 120,
                "crs": "EPSG:4326",
                "status": "COMPLETED",
                "geometry_summary": {
                    "Polygon": 45,
                    "LineString": 50,
                    "Point": 25
                },
                "created_at": "2026-10-07T12:00:00Z",
                "error_message": None
            }
        }
    }


class FeatureMeasurement(BaseModel):
    """Measurement calculation results for a single geospatial feature."""
    feature_id: Union[int, str] = Field(..., description="Identifier or index of the feature")
    geometry_type: str = Field(..., description="GeoJSON geometry type (e.g. Polygon, LineString, Point)")
    measurement_type: str = Field(
        ...,
        description="Type of measurement computed ('area', 'length', 'none', 'unsupported')"
    )
    value: Optional[float] = Field(
        None,
        description="Calculated value in base SI units (m² for area, m for length, None for point)"
    )
    unit: Optional[str] = Field(
        None,
        description="Base measurement unit ('square_meters', 'meters', or None)"
    )
    formatted_value: str = Field(
        ...,
        description="Human-readable formatted measurement with unit label"
    )
    projected_crs: Optional[str] = Field(
        None,
        description="Projected CRS used for metric calculations (e.g., 'EPSG:32643')"
    )
    additional_units: Optional[Dict[str, float]] = Field(
        default=None,
        description="Measurements converted to standard alternative units (hectares, km², km, etc.)"
    )
    perimeter_or_length_meters: Optional[float] = Field(
        default=None,
        description="Boundary perimeter for polygons or total length for lines"
    )
    geodesic_value: Optional[float] = Field(
        default=None,
        description="High-precision WGS84 geodesic calculation for validation"
    )
    status: str = Field(
        default="success",
        description="Calculation status: 'success', 'skipped_point', 'unsupported', or 'error'"
    )
    message: Optional[str] = Field(
        default=None,
        description="Explanatory message or warning (e.g. why no measurement was performed)"
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Attribute table / property dictionary of the feature"
    )
    geometry: Optional[Dict[str, Any]] = Field(
        default=None,
        description="GeoJSON geometry representation (optional)"
    )


class DatasetMeasurementSummary(BaseModel):
    """Aggregate measurements across all features in the dataset."""
    total_features: int = 0
    polygon_count: int = 0
    linestring_count: int = 0
    point_count: int = 0
    unsupported_count: int = 0
    total_area_sq_meters: float = 0.0
    total_area_hectares: float = 0.0
    total_area_sq_km: float = 0.0
    total_length_meters: float = 0.0
    total_length_km: float = 0.0


class FileMeasurementsResponse(BaseModel):
    """Full measurement response for an uploaded geospatial file."""
    file_id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Original filename")
    source_crs: str = Field(..., description="Source Coordinate Reference System")
    total_features: int = Field(..., description="Total number of features processed")
    summary: DatasetMeasurementSummary = Field(..., description="Aggregate summary metrics")
    features: List[FeatureMeasurement] = Field(..., description="Feature-by-feature measurement details")


class GeoJSONFeature(BaseModel):
    """Standard GeoJSON Feature representation."""
    type: str = "Feature"
    id: Union[int, str]
    geometry: Dict[str, Any]
    properties: Dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    """Standard GeoJSON FeatureCollection."""
    type: str = "FeatureCollection"
    crs: Optional[Dict[str, Any]] = None
    features: List[GeoJSONFeature]


class HealthCheckResponse(BaseModel):
    """Service health and environment status."""
    status: str = "healthy"
    version: str
    geospatial_backend: Dict[str, Any]
    supported_file_types: List[str]
