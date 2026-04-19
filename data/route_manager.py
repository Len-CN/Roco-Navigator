"""
路线管理

负责路线的保存、加载和管理。
"""

import logging
import os
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from ..utils.file_utils import load_json, save_json, get_data_dir

logger = logging.getLogger(__name__)


@dataclass
class Route:
    """路线"""
    id: str
    name: str
    targets: List[Tuple[float, float]]   # [(x, y), ...]
    total_distance: float = 0.0
    strategy: str = "nearest"            # "nearest", "optimal", "custom"
    map_id: str = "default"
    created: str = ""
    description: str = ""


class RouteManager:
    """路线管理器"""

    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            data_path = os.path.join(get_data_dir(), "routes.json")

        self._data_path = data_path
        self._routes: List[Route] = []

        logger.info("RouteManager initialized")

    def load(self) -> bool:
        data = load_json(self._data_path, default={"routes": []})
        if data is None:
            return False

        self._routes = []
        for item in data.get("routes", []):
            try:
                targets = [(t["x"], t["y"]) for t in item.get("targets", [])]
                route = Route(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    targets=targets,
                    total_distance=float(item.get("total_distance", 0)),
                    strategy=item.get("strategy", "nearest"),
                    map_id=item.get("map_id", "default"),
                    created=item.get("created", ""),
                    description=item.get("description", ""),
                )
                self._routes.append(route)
            except Exception as e:
                logger.warning("Failed to parse route: %s", e)

        logger.info("Loaded %d routes", len(self._routes))
        return True

    def save(self) -> bool:
        data = {
            "version": "1.0.0",
            "last_updated": datetime.now().isoformat(),
            "routes": [
                {
                    "id": r.id, "name": r.name,
                    "targets": [{"x": t[0], "y": t[1]} for t in r.targets],
                    "total_distance": r.total_distance,
                    "strategy": r.strategy,
                    "map_id": r.map_id,
                    "created": r.created,
                    "description": r.description,
                }
                for r in self._routes
            ]
        }
        return save_json(self._data_path, data)

    def get_all(self) -> List[Route]:
        return self._routes.copy()

    def get_by_id(self, route_id: str) -> Optional[Route]:
        for r in self._routes:
            if r.id == route_id:
                return r
        return None

    def add(self, route: Route) -> bool:
        if not route.created:
            route.created = datetime.now().isoformat()
        self._routes.append(route)
        return True

    def update(self, route: Route) -> bool:
        for i, r in enumerate(self._routes):
            if r.id == route.id:
                self._routes[i] = route
                return True
        return False

    def delete(self, route_id: str) -> bool:
        for i, r in enumerate(self._routes):
            if r.id == route_id:
                self._routes.pop(i)
                return True
        return False

    def clear(self):
        self._routes.clear()

    @property
    def count(self) -> int:
        return len(self._routes)
