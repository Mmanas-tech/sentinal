"""Offline satellite change-analysis primitives."""
from .change_detection import analyze_change, difference_mask
from .indices import spectral_indices, classify_land_cover
from .hotspots import rank_hotspots
from .raster import analyze_rasters
