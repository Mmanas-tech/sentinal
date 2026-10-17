import importlib.util

import numpy as np
import pytest

from sentinal.modules.satellite import analyze_rasters


def test_real_raster_path_is_explicitly_unavailable_without_rasterio(tmp_path) -> None:
    if importlib.util.find_spec("rasterio") is not None:
        pytest.skip("Rasterio is installed; real fixture coverage belongs to the Rasterio test environment")
    result = analyze_rasters(tmp_path / "before.tif", tmp_path / "after.tif")

    assert result["status"] == "UNAVAILABLE"
    assert result["provenance"]["mode"] == "REAL_RASTER"


@pytest.mark.skipif(importlib.util.find_spec("rasterio") is None, reason="Rasterio optional dependency is not installed")
def test_geotiff_change_is_georeferenced_and_preserves_provenance(tmp_path) -> None:
    import rasterio
    from rasterio.transform import from_origin

    transform = from_origin(13.0, 52.0, 0.01, 0.01)
    before_path = tmp_path / "before.tif"
    after_path = tmp_path / "after.tif"
    before = np.full((4, 4), 10, dtype="float32")
    after = before.copy()
    after[1:3, 1:3] = 20
    before[0, 0] = -9999
    with rasterio.open(before_path, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32", crs="EPSG:4326", transform=transform, nodata=-9999) as dataset:
        dataset.write(before, 1)
        dataset.update_tags(ACQUISITION_DATE="2026-01-01T00:00:00Z")
    with rasterio.open(after_path, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32", crs="EPSG:4326", transform=transform, nodata=-9999) as dataset:
        dataset.write(after, 1)
        dataset.update_tags(ACQUISITION_DATE="2026-01-02T00:00:00Z")

    result = analyze_rasters(before_path, after_path, threshold=0.5)

    assert result["status"] == "ok"
    assert result["changed_fraction"] == pytest.approx(4 / 15)
    assert result["provenance"]["alignment"] == "already_aligned"
    assert result["provenance"]["before"]["acquisition"] == "2026-01-01T00:00:00Z"
    assert result["hotspots"][0]["geometry"]["type"] == "Polygon"
    assert len(result["hotspots"][0]["coordinates"]) == 2


@pytest.mark.skipif(importlib.util.find_spec("rasterio") is None, reason="Rasterio optional dependency is not installed")
def test_geotiff_crs_or_grid_mismatch_is_aligned(tmp_path) -> None:
    import rasterio
    from rasterio.transform import from_origin

    before_path = tmp_path / "before.tif"
    after_path = tmp_path / "after.tif"
    with rasterio.open(before_path, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32", crs="EPSG:4326", transform=from_origin(13, 52, 0.01, 0.01)) as dataset:
        dataset.write(np.ones((4, 4), dtype="float32"), 1)
    with rasterio.open(after_path, "w", driver="GTiff", height=2, width=2, count=1, dtype="float32", crs="EPSG:4326", transform=from_origin(13, 52, 0.02, 0.02)) as dataset:
        dataset.write(np.full((2, 2), 2, dtype="float32"), 1)

    result = analyze_rasters(before_path, after_path, threshold=0.5)

    assert result["status"] == "ok"
    assert result["provenance"]["alignment"] == "reprojected_to_before_grid"
