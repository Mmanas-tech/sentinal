"""Asset registry and dependency cascade calculations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

import yaml


@dataclass(frozen=True)
class Asset:
    id: str
    name: str = ""
    type: str = ""
    importance: float = 50.0
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    lat: float | None = None
    lon: float | None = None

    @property
    def depends_on(self) -> tuple[str, ...]:
        return self.dependencies


class AssetRegistry:
    """Validated asset/dependency graph used by the risk engine."""

    def __init__(self, assets: Iterable[Asset] = ()) -> None:
        self._assets = {asset.id: asset for asset in assets}
        self._validate()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AssetRegistry":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        default_importance = float(data.get("default_importance", 50))
        assets = []
        for raw in data.get("assets", []):
            assets.append(
                Asset(
                    id=str(raw["id"]),
                    name=str(raw.get("name", "")),
                    type=str(raw.get("type", "")),
                    importance=float(raw.get("importance", default_importance)),
                    dependencies=tuple(raw.get("depends_on", raw.get("dependencies", []))),
                    lat=raw.get("lat"),
                    lon=raw.get("lon"),
                )
            )
        return cls(assets)

    def add(self, asset: Asset) -> None:
        """Add or replace an asset, rolling back if the graph becomes invalid."""
        if not asset.id:
            raise ValueError("asset id is required")
        if not 0 <= asset.importance <= 100:
            raise ValueError(f"asset {asset.id} importance must be 0-100")
        previous = self._assets.get(asset.id)
        self._assets[asset.id] = asset
        try:
            self._validate()
        except Exception:
            if previous is None:
                self._assets.pop(asset.id, None)
            else:
                self._assets[asset.id] = previous
            raise

    def get(self, asset_id: str) -> Asset:
        try:
            return self._assets[asset_id]
        except KeyError as exc:
            raise ValueError(f"unknown asset: {asset_id}") from exc

    def __iter__(self):
        return iter(self._assets.values())

    def _validate(self) -> None:
        for asset in self._assets.values():
            missing = set(asset.dependencies).difference(self._assets)
            if missing:
                names = ", ".join(sorted(missing))
                raise ValueError(f"asset {asset.id} has missing dependencies: {names}")
            if not 0 <= asset.importance <= 100:
                raise ValueError(f"asset {asset.id} importance must be 0-100")

        visiting: set[str] = set()
        complete: set[str] = set()

        def visit(asset_id: str, path: list[str]) -> None:
            if asset_id in visiting:
                raise ValueError(f"circular asset dependency: {' -> '.join(path + [asset_id])}")
            if asset_id in complete:
                return
            visiting.add(asset_id)
            for dependency in self._assets[asset_id].dependencies:
                visit(dependency, path + [asset_id])
            visiting.remove(asset_id)
            complete.add(asset_id)

        for asset_id in self._assets:
            visit(asset_id, [])

    def highest_dependency_risk(
        self,
        asset_id: str,
        scores: Mapping[str, float],
    ) -> float:
        """Find the highest known risk anywhere below an asset."""
        visited: set[str] = set()

        def visit(current: str) -> float:
            if current in visited:
                return 0.0
            visited.add(current)
            asset = self.get(current)
            return max(
                [float(scores.get(current, 0.0))]
                + [visit(dependency) for dependency in asset.dependencies]
            )

        return max(
            [visit(dependency) for dependency in self.get(asset_id).dependencies] or [0.0]
        )

    def cascade_boost(
        self,
        asset_id: str,
        scores: Mapping[str, float],
        fraction: float,
    ) -> float:
        return fraction * self.highest_dependency_risk(asset_id, scores)
