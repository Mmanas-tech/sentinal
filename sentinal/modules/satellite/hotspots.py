"""Connected changed-region extraction for synthetic satellite masks."""

from collections import deque

import numpy as np


def rank_hotspots(difference_mask, score=None, top_n=10):
    """Return connected changed regions ranked by severity and area."""
    mask = np.asarray(difference_mask, bool)
    values = np.asarray(score if score is not None else mask, float)
    if mask.ndim != 2 or values.shape != mask.shape:
        raise ValueError("difference mask and score must be matching 2D arrays")
    visited = np.zeros(mask.shape, dtype=bool)
    regions = []
    height, width = mask.shape
    for row in range(height):
        for col in range(width):
            if not mask[row, col] or visited[row, col]:
                continue
            queue = deque([(row, col)])
            visited[row, col] = True
            pixels = []
            while queue:
                current_row, current_col = queue.popleft()
                pixels.append((current_row, current_col))
                for next_row, next_col in (
                    (current_row - 1, current_col),
                    (current_row + 1, current_col),
                    (current_row, current_col - 1),
                    (current_row, current_col + 1),
                ):
                    if (
                        0 <= next_row < height
                        and 0 <= next_col < width
                        and mask[next_row, next_col]
                        and not visited[next_row, next_col]
                    ):
                        visited[next_row, next_col] = True
                        queue.append((next_row, next_col))
            region_values = [float(values[y, x]) for y, x in pixels]
            rows = [y for y, _ in pixels]
            cols = [x for _, x in pixels]
            regions.append(
                {
                    "region_id": f"hotspot_{len(regions) + 1}",
                    "size": len(pixels),
                    "severity": max(region_values),
                    "mean_score": sum(region_values) / len(region_values),
                    "bounds": [min(rows), min(cols), max(rows) + 1, max(cols) + 1],
                    "pixels": [{"row": y, "col": x} for y, x in pixels],
                }
            )
    return sorted(regions, key=lambda item: (item["severity"], item["size"]), reverse=True)[:top_n]
