import logging
from typing import List

try:
    from shapely.geometry import Polygon, shape, mapping, box
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

logger = logging.getLogger("splitter")


class SubParcel:
    def __init__(self, index: int, name: str, geojson: dict, area_ha: float,
                 assigned_machine: str | None = None):
        self.index = index
        self.name = name
        self.geojson = geojson
        self.area_ha = area_ha
        self.assigned_machine = assigned_machine

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "geojson": self.geojson,
            "area_ha": self.area_ha,
            "assigned_machine": self.assigned_machine,
        }


class ParcelSplitter:

    def split(self, geojson: dict, mode: str = "strip", count: int = 1,
              angle_deg: float | None = None, machine_assignments: dict[str, str] | None = None,
              parcel_name: str = "Field") -> List[SubParcel]:

        if not HAS_SHAPELY:
            raise RuntimeError("shapely is required for parcel splitting")

        if count < 1:
            raise ValueError("split count must be >= 1")

        polygon = self._parse_polygon(geojson)
        if polygon is None or polygon.is_empty:
            raise ValueError("invalid GeoJSON polygon")

        if count == 1:
            return [self._single_parcel(polygon, geojson, parcel_name, 0, machine_assignments)]

        if mode == "strip":
            return self._strip_split(polygon, count, angle_deg, parcel_name, machine_assignments)
        elif mode == "checkerboard":
            return self._checkerboard_split(polygon, count, parcel_name, machine_assignments)
        else:
            raise ValueError(f"unknown split mode: {mode}")

    def _parse_polygon(self, geojson: dict):
        try:
            geom = geojson.get("geometry", geojson)
            coords = geom.get("coordinates")
            if coords is None:
                return None
            poly_type = geom.get("type", "Polygon")
            if poly_type == "Polygon":
                return shape({"type": "Polygon", "coordinates": coords})
            elif poly_type == "MultiPolygon":
                return shape({"type": "MultiPolygon", "coordinates": coords})
        except Exception:
            return None
        return None

    def _single_parcel(self, polygon, geojson, name, index, assignments=None) -> SubParcel:
        area_m2 = polygon.area
        area_ha = round(area_m2 / 10000, 4)
        machine = None
        if assignments:
            machine = assignments.get(str(index))
        return SubParcel(index=index, name=name, geojson=geojson, area_ha=area_ha,
                         assigned_machine=machine)

    def _strip_split(self, polygon, count, angle_deg, name, assignments) -> List[SubParcel]:
        import math
        min_rotated = polygon.minimum_rotated_rectangle
        coords = list(min_rotated.exterior.coords)

        edges = []
        for i in range(len(coords) - 1):
            dx = coords[i + 1][0] - coords[i][0]
            dy = coords[i + 1][1] - coords[i][1]
            edges.append((math.sqrt(dx * dx + dy * dy), dx, dy))
        edges.sort(key=lambda e: e[0], reverse=True)

        if angle_deg is not None:
            rad = math.radians(angle_deg)
            cut_dx = math.sin(rad)
            cut_dy = math.cos(rad)
        else:
            _, longest_dx, longest_dy = edges[0]
            length = math.sqrt(longest_dx * longest_dx + longest_dy * longest_dy)
            if length > 0:
                longest_dx /= length
                longest_dy /= length
            cut_dx = -longest_dy
            cut_dy = longest_dx

        vertices = list(polygon.exterior.coords)
        projections = [v[0] * cut_dx + v[1] * cut_dy for v in vertices]
        proj_min, proj_max = min(projections), max(projections)

        strip_width = (proj_max - proj_min) / count

        results = []
        for i in range(count):
            lo = proj_min + i * strip_width
            hi = proj_min + (i + 1) * strip_width if i < count - 1 else proj_max + 1

            cut_poly = self._clip_strip(polygon, cut_dx, cut_dy, lo, hi)

            if cut_poly.is_empty:
                logger.warning(f"Strip {i} is empty, skipping")
                continue

            simplified = cut_poly.simplify(0.01, preserve_topology=True)
            geojson = self._to_geojson(simplified)
            area_ha = round(simplified.area / 10000, 4)
            machine = assignments.get(str(i)) if assignments else None

            results.append(SubParcel(
                index=i, name=f"{name} — Section {i + 1}",
                geojson=geojson, area_ha=area_ha, assigned_machine=machine,
            ))

        return results

    def _clip_strip(self, polygon, cut_dx, cut_dy, lo, hi):
        x0 = lo * cut_dx - 1000 * cut_dy
        y0 = lo * cut_dy + 1000 * cut_dx
        x1 = hi * cut_dx - 1000 * cut_dy
        y1 = hi * cut_dy + 1000 * cut_dx
        x2 = hi * cut_dx + 1000 * cut_dy
        y2 = hi * cut_dy - 1000 * cut_dx
        x3 = lo * cut_dx + 1000 * cut_dy
        y3 = lo * cut_dy - 1000 * cut_dx

        strip_box = Polygon([(x0, y0), (x1, y1), (x2, y2), (x3, y3), (x0, y0)])

        result = polygon.intersection(strip_box)
        if result.is_empty:
            return result
        if result.geom_type == "GeometryCollection":
            polys = [g for g in result.geoms if g.geom_type == "Polygon"]
            if not polys:
                return Polygon()
            return max(polys, key=lambda p: p.area)
        return result

    def _checkerboard_split(self, polygon, count, name, assignments) -> List[SubParcel]:
        import math
        bounds = polygon.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]

        cols = max(1, round(math.sqrt(count * width / height)))
        rows = max(1, (count + cols - 1) // cols)

        cell_w = width / cols
        cell_h = height / rows

        results = []
        idx = 0
        for r in range(rows):
            for c in range(cols):
                if idx >= count:
                    break
                cx = bounds[0] + c * cell_w
                cy = bounds[1] + r * cell_h
                cell = box(cx, cy, cx + cell_w, cy + cell_h)
                clipped = polygon.intersection(cell)
                if not clipped.is_empty:
                    simplified = clipped.simplify(0.01, preserve_topology=True)
                    geojson = self._to_geojson(simplified)
                    area_ha = round(simplified.area / 10000, 4)
                    machine = assignments.get(str(idx)) if assignments else None
                    results.append(SubParcel(
                        index=idx, name=f"{name} — Cell {idx + 1}",
                        geojson=geojson, area_ha=area_ha, assigned_machine=machine,
                    ))
                idx += 1

        return results

    def _to_geojson(self, geom) -> dict:
        m = mapping(geom)
        return {"type": "Feature", "geometry": m, "properties": {}}
