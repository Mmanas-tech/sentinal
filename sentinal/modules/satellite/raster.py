"""Real GeoTIFF change processing (optional Rasterio dependency).

This module deliberately never falls back to the numeric demo pipeline.  A
missing Rasterio installation is reported as ``UNAVAILABLE``.
"""
from __future__ import annotations

from collections import deque
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np


def _open(source):
    try:
        import rasterio
    except ImportError:
        return None, "Rasterio is not installed; real raster processing is UNAVAILABLE", None
    if isinstance(source, (bytes, bytearray)):
        memory_file = rasterio.io.MemoryFile(bytes(source))
        return rasterio.open(memory_file), None, memory_file
    path = Path(source)
    if not path.is_file():
        return None, f"raster path does not exist: {path}", None
    return rasterio.open(path), None, None


def _meta(ds, name: str):
    if not ds.crs:
        raise ValueError(f"{name} has no CRS")
    if ds.width < 1 or ds.height < 1:
        raise ValueError(f"{name} has invalid dimensions")
    tags = ds.tags()
    acquisition = tags.get("ACQUISITION_DATE") or tags.get("DATE_ACQUIRED") or tags.get("datetime")
    return {"path": name, "crs": ds.crs.to_string(), "width": ds.width, "height": ds.height,
            "bounds": list(ds.bounds), "transform": list(ds.transform), "count": ds.count,
            "nodata": ds.nodata, "acquisition": acquisition, "tags": tags}


def analyze_rasters(before, after, *, before_band=1, after_band=1, threshold=.15,
                    resampling="bilinear") -> dict[str, Any]:
    """Compare two real rasters and return georeferenced change results."""
    b, err, b_memory = _open(before)
    if err:
        return {"status": "UNAVAILABLE", "reason": err, "provenance": {"mode": "REAL_RASTER"}}
    a, err, a_memory = _open(after)
    if err:
        b.close()
        if b_memory is not None:
            b_memory.close()
        return {"status": "UNAVAILABLE", "reason": err, "provenance": {"mode": "REAL_RASTER"}}
    try:
        bm, am = _meta(b, "before"), _meta(a, "after")
        for ds, band, name in ((b, before_band, "before_band"), (a, after_band, "after_band")):
            if not isinstance(band, int) or band < 1 or band > ds.count:
                raise ValueError(f"{name} {band} is unavailable (dataset has {ds.count} bands)")
        if b.crs != a.crs:
            # reprojection below is valid only when both CRS are known.
            if not b.crs or not a.crs:
                raise ValueError("CRS mismatch cannot be aligned without CRS")
        before_arr = b.read(before_band, masked=True).filled(np.nan).astype(float)
        if b.shape != a.shape or b.transform != a.transform or b.crs != a.crs:
            from rasterio.warp import reproject, calculate_default_transform
            from rasterio.enums import Resampling
            target = np.full(b.shape, np.nan, dtype=float)
            rs = getattr(Resampling, resampling, Resampling.bilinear)
            reproject(a.read(after_band), target, src_transform=a.transform, src_crs=a.crs,
                      dst_transform=b.transform, dst_crs=b.crs, src_nodata=a.nodata,
                      dst_nodata=np.nan, resampling=rs)
            aligned = target
            alignment = "reprojected_to_before_grid"
        else:
            aligned = a.read(after_band, masked=True).filled(np.nan).astype(float)
            alignment = "already_aligned"
        valid = np.isfinite(before_arr) & np.isfinite(aligned)
        if not valid.any():
            raise ValueError("rasters contain no overlapping valid pixels")
        diff = np.abs(aligned - before_arr) / np.maximum(np.abs(before_arr), 1e-9)
        diff[~valid] = np.nan
        mask = valid & (diff >= float(threshold))
        bounded_diff = np.minimum(diff, 1.0)
        regions = _regions(mask, diff, b.transform)
        return {"status": "ok", "difference_mask": mask, "percent_change": float(np.nanmean(bounded_diff) * 100),
                "changed_fraction": float(mask.sum() / valid.sum()),
                "confidence": float(valid.sum() / mask.size), "hotspots": regions,
                "provenance": {"mode": "REAL_RASTER", "before": bm, "after": am,
                                "alignment": alignment, "parameters": {"before_band": before_band,
                                "after_band": after_band, "threshold": threshold, "resampling": resampling}}}
    except (ValueError, TypeError, ImportError) as exc:
        return {"status": "refused", "reason": str(exc), "provenance": {"mode": "REAL_RASTER"}}
    finally:
        b.close(); a.close()
        if b_memory is not None:
            b_memory.close()
        if a_memory is not None:
            a_memory.close()


def _regions(mask, score, transform):
    seen = np.zeros(mask.shape, bool); out = []
    for y, x in zip(*np.where(mask & ~seen)):
        if seen[y, x]: continue
        q, pix = deque([(y, x)]), [] ; seen[y, x] = True
        while q:
            cy, cx = q.popleft(); pix.append((cy, cx))
            for ny, nx in ((cy-1,cx),(cy+1,cx),(cy,cx-1),(cy,cx+1)):
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny,nx] and not seen[ny,nx]:
                    seen[ny,nx] = True; q.append((ny,nx))
        rows, cols = zip(*pix); minx, miny = transform @ (min(cols), max(rows)+1); maxx, maxy = transform @ (max(cols)+1, min(rows))
        centers = [transform @ (x+.5, y+.5) for y, x in pix]
        out.append({"region_id": f"hotspot_{len(out)+1}", "size": len(pix), "severity": float(np.nanmax([score[p] for p in pix])),
                    "geometry": {"type":"Polygon", "coordinates":[[[minx,miny],[maxx,miny],[maxx,maxy],[minx,maxy],[minx,miny]]]},
                    "coordinates": [float(sum(p[0] for p in centers)/len(centers)), float(sum(p[1] for p in centers)/len(centers))]})
    return out
