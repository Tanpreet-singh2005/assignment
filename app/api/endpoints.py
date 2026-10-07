import os
import uuid
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse

from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_BYTES, UPLOAD_DIR
from app.core.measurements import MeasurementService
from app.core.parsers import GeospatialFileParser, GeospatialParserError
from app.models.database import FileRepository
from app.models.schemas import (
    FileInfoResponse,
    FileMeasurementsResponse,
    DatasetMeasurementSummary,
    GeoJSONFeatureCollection,
    GeoJSONFeature,
    HealthCheckResponse
)

router = APIRouter(prefix="/api", tags=["Geospatial Files & Measurements"])


@router.post(
    "/files/",
    response_model=FileInfoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a geospatial file (.zip Shapefile or .kml)",
    description="Uploads a zipped Shapefile or KML file, extracts all features, computes metric measurements via optimal projected CRS, and persists records."
)
async def upload_geospatial_file(
    file: UploadFile = File(..., description="Zipped Shapefile (.zip) or KML file (.kml)")
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename cannot be empty.")

    original_filename = file.filename
    file_ext = Path(original_filename).suffix.lower()

    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{file_ext}'. Allowed formats are .zip (Shapefile) and .kml."
        )

    file_id = str(uuid.uuid4())
    detected_type = "shapefile" if file_ext == ".zip" else "kml"

    # Save uploaded file to disk
    file_storage_path = UPLOAD_DIR / f"{file_id}_{original_filename}"
    file_size = 0

    try:
        with open(file_storage_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                file_size += len(chunk)
                if file_size > MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)} MB."
                    )
                buffer.write(chunk)
    except HTTPException:
        if file_storage_path.exists():
            file_storage_path.unlink()
        raise
    except Exception as e:
        if file_storage_path.exists():
            file_storage_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    # Create initial file record in repository
    FileRepository.create_file_record(
        file_id=file_id,
        filename=original_filename,
        file_type=detected_type,
        file_size_bytes=file_size,
        status="PROCESSING",
        storage_path=str(file_storage_path)
    )

    # Process and compute measurements
    try:
        features, crs_str, geom_summary = GeospatialFileParser.parse_file(file_storage_path, original_filename)

        measurements_list = []
        total_area = 0.0
        total_length = 0.0
        polygon_cnt = 0
        linestring_cnt = 0
        point_cnt = 0
        unsupported_cnt = 0

        for f in features:
            f_meas = MeasurementService.calculate_feature_measurement(
                feature_id=f["feature_id"],
                geometry=f["geometry"],
                source_crs=f["source_crs"],
                properties=f["properties"],
                include_geometry_geojson=True
            )
            measurements_list.append(f_meas.model_dump())

            # Accumulate dataset totals
            if f_meas.measurement_type == "area" and f_meas.value is not None:
                total_area += f_meas.value
                polygon_cnt += 1
            elif f_meas.measurement_type == "length" and f_meas.value is not None:
                total_length += f_meas.value
                linestring_cnt += 1
            elif f_meas.measurement_type == "none":
                point_cnt += 1
            elif f_meas.measurement_type == "unsupported":
                unsupported_cnt += 1

        summary_data = {
            "total_features": len(features),
            "polygon_count": polygon_cnt,
            "linestring_count": linestring_cnt,
            "point_count": point_cnt,
            "unsupported_count": unsupported_cnt,
            "total_area_sq_meters": round(total_area, 2),
            "total_area_hectares": round(total_area / 10000.0, 4),
            "total_area_sq_km": round(total_area / 1000000.0, 6),
            "total_length_meters": round(total_length, 2),
            "total_length_km": round(total_length / 1000.0, 4)
        }

        # Save measurements into repository
        FileRepository.save_measurements(file_id, summary_data, measurements_list)

        # Update file record status
        FileRepository.update_file_record(
            file_id=file_id,
            status="COMPLETED",
            feature_count=len(features),
            crs=crs_str,
            geometry_summary=geom_summary
        )

        record = FileRepository.get_file(file_id)
        return FileInfoResponse(**record)

    except GeospatialParserError as e:
        FileRepository.update_file_record(
            file_id=file_id,
            status="FAILED",
            error_message=str(e)
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        FileRepository.update_file_record(
            file_id=file_id,
            status="FAILED",
            error_message=f"Processing error: {str(e)}"
        )
        raise HTTPException(status_code=500, detail=f"An error occurred while processing the geospatial file: {str(e)}")


@router.get(
    "/files/{file_id}/",
    response_model=FileInfoResponse,
    summary="Get file information and processing status",
    description="Returns metadata about an uploaded geospatial file including status, CRS, and feature count."
)
async def get_file_info(file_id: str):
    record = FileRepository.get_file(file_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"File with ID '{file_id}' was not found.")
    return FileInfoResponse(**record)


@router.get(
    "/files/{file_id}/measurements/",
    response_model=FileMeasurementsResponse,
    summary="Get calculated measurements for features in the file",
    description="Returns accurate metric measurements (area for polygons, length for linestrings, skipped points) and aggregate metrics."
)
async def get_file_measurements(
    file_id: str,
    include_geometry: bool = Query(
        False,
        description="Whether to include full GeoJSON geometry coordinates in each feature response"
    )
):
    record = FileRepository.get_file(file_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"File with ID '{file_id}' was not found.")

    if record["status"] == "PROCESSING":
        raise HTTPException(status_code=202, detail="File is still being processed. Please retry shortly.")

    if record["status"] == "FAILED":
        raise HTTPException(status_code=400, detail=f"File processing failed: {record.get('error_message')}")

    meas_data = FileRepository.get_measurements(file_id)
    if not meas_data:
        raise HTTPException(status_code=404, detail=f"No measurements found for file ID '{file_id}'.")

    features = meas_data["features"]
    if not include_geometry:
        # Strip geometry payload if not explicitly requested for smaller payload
        cleaned_features = []
        for feat in features:
            f_copy = dict(feat)
            f_copy["geometry"] = None
            cleaned_features.append(f_copy)
        features = cleaned_features

    return FileMeasurementsResponse(
        file_id=record["id"],
        filename=record["filename"],
        source_crs=record["crs"],
        total_features=record["feature_count"],
        summary=DatasetMeasurementSummary(**meas_data["summary"]),
        features=features
    )


@router.get(
    "/files/{file_id}/features/",
    response_model=GeoJSONFeatureCollection,
    summary="Get features as standard GeoJSON FeatureCollection",
    description="Returns all features with GeoJSON geometries, property attributes, and measurement metadata."
)
async def get_file_features_geojson(file_id: str):
    record = FileRepository.get_file(file_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"File with ID '{file_id}' was not found.")

    meas_data = FileRepository.get_measurements(file_id)
    if not meas_data:
        raise HTTPException(status_code=404, detail="No feature data found.")

    geojson_features = []
    for f in meas_data["features"]:
        geom = f.get("geometry") or {"type": "Point", "coordinates": [0, 0]}
        props = dict(f.get("properties") or {})
        props["_measurement_type"] = f.get("measurement_type")
        props["_measurement_value"] = f.get("value")
        props["_measurement_unit"] = f.get("unit")
        props["_formatted_value"] = f.get("formatted_value")
        props["_projected_crs"] = f.get("projected_crs")

        geojson_features.append(
            GeoJSONFeature(
                id=f["feature_id"],
                geometry=geom,
                properties=props
            )
        )

    return GeoJSONFeatureCollection(
        crs={"type": "name", "properties": {"name": record["crs"]}},
        features=geojson_features
    )


@router.get(
    "/files/",
    response_model=List[FileInfoResponse],
    summary="List all uploaded geospatial files",
    description="Retrieve a paginated list of uploaded files with their current status and metadata."
)
async def list_files(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of files to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    files = FileRepository.list_files(limit=limit, offset=offset)
    return [FileInfoResponse(**f) for f in files]


@router.delete(
    "/files/{file_id}/",
    status_code=status.HTTP_200_OK,
    summary="Delete an uploaded file and its measurements",
    description="Removes the file record, calculated measurements, and stored file from disk."
)
async def delete_file(file_id: str):
    record = FileRepository.get_file(file_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"File with ID '{file_id}' was not found.")

    # Remove file on disk if exists
    storage_path = record.get("storage_path")
    if storage_path and os.path.exists(storage_path):
        try:
            os.remove(storage_path)
        except Exception:
            pass

    deleted = FileRepository.delete_file(file_id)
    return {"message": f"File '{file_id}' and all associated measurements have been deleted successfully."}


@router.get(
    "/health/",
    response_model=HealthCheckResponse,
    summary="Service Health and Geospatial Engine Status",
    description="Checks the health of the API, GDAL/Pyogrio drivers, and PyProj CRS projection engine."
)
async def health_check():
    import pyproj
    import shapely
    import pyogrio

    return HealthCheckResponse(
        status="healthy",
        version="1.0.0",
        geospatial_backend={
            "pyproj_version": pyproj.__version__,
            "shapely_version": shapely.__version__,
            "pyogrio_version": pyogrio.__version__,
            "kml_driver_available": "KML" in pyogrio.list_drivers(),
            "shapefile_driver_available": "ESRI Shapefile" in pyogrio.list_drivers()
        },
        supported_file_types=[".zip (Shapefile)", ".kml (KML Document)"]
    )
