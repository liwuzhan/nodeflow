import math
from typing import Any, Callable

from shapely.geometry import mapping, shape
from shapely.ops import transform


def _geometry_payload(geojson: dict[str, Any]) -> dict[str, Any]:
    return geojson.get("geometry", geojson)


def parse_wgs84_geometry(geojson: dict[str, Any]):
    geom = shape(_geometry_payload(geojson))
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("GeoJSON must contain a Polygon or MultiPolygon")
    if geom.is_empty or not geom.is_valid:
        raise ValueError("GeoJSON contains an empty or invalid polygon")
    return geom


def local_reference(geometry) -> tuple[float, float]:
    point = geometry.representative_point()
    return float(point.x), float(point.y)


def _meters_per_degree(latitude_deg: float) -> tuple[float, float]:
    latitude = math.radians(latitude_deg)
    lat_scale = (
        111132.92
        - 559.82 * math.cos(2.0 * latitude)
        + 1.175 * math.cos(4.0 * latitude)
        - 0.0023 * math.cos(6.0 * latitude)
    )
    lon_scale = (
        111412.84 * math.cos(latitude)
        - 93.5 * math.cos(3.0 * latitude)
        + 0.118 * math.cos(5.0 * latitude)
    )
    return lon_scale, lat_scale


def _coordinate_transform(
    x_fn: Callable[[float], float],
    y_fn: Callable[[float], float],
):
    def apply(x, y, z=None):
        if hasattr(x, "__iter__"):
            xs = [x_fn(float(value)) for value in x]
            ys = [y_fn(float(value)) for value in y]
            return (xs, ys, z) if z is not None else (xs, ys)
        tx = x_fn(float(x))
        ty = y_fn(float(y))
        return (tx, ty, z) if z is not None else (tx, ty)

    return apply


def project_to_local(geometry, ref_lon: float, ref_lat: float):
    lon_scale, lat_scale = _meters_per_degree(ref_lat)
    return transform(
        _coordinate_transform(
            lambda lon: (lon - ref_lon) * lon_scale,
            lambda lat: (lat - ref_lat) * lat_scale,
        ),
        geometry,
    )


def unproject_from_local(geometry, ref_lon: float, ref_lat: float):
    lon_scale, lat_scale = _meters_per_degree(ref_lat)
    return transform(
        _coordinate_transform(
            lambda x: ref_lon + x / lon_scale,
            lambda y: ref_lat + y / lat_scale,
        ),
        geometry,
    )


def area_hectares(geojson: dict[str, Any]) -> float:
    geometry = parse_wgs84_geometry(geojson)
    ref_lon, ref_lat = local_reference(geometry)
    projected = project_to_local(geometry, ref_lon, ref_lat)
    return round(float(projected.area) / 10000.0, 4)


def to_feature(geometry) -> dict[str, Any]:
    return {"type": "Feature", "geometry": mapping(geometry), "properties": {}}
