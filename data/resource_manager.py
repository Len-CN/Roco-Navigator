"""
资源点管理

负责加载、筛选、编辑资源点数据。
"""

import logging
import os
from typing import Optional, List, Dict, Set
from dataclasses import dataclass
from datetime import datetime

from ..utils.file_utils import load_json, save_json, get_data_dir

logger = logging.getLogger(__name__)


@dataclass
class Resource:
    """资源点"""
    id: str
    name: str
    type: str               # "地点", "精灵分布", "宝箱", "收集", "采集", "战斗", "任务"
    x: float
    y: float
    map_id: str = "default"
    mark_type: int = 0
    mark_type_name: str = ""   # 细分类名 (e.g., "庇护所", "传送点", "一尾凤")
    icon_url: str = ""
    description: str = ""
    source: str = "manual"   # "wiki" or "manual"
    last_updated: str = ""


class ResourceManager:
    """
    资源点管理器

    功能:
    - 加载和保存资源数据
    - 按类型/地图/关键词筛选
    - 增删改查
    """

    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            data_path = os.path.join(get_data_dir(), "resources.json")

        self._data_path = data_path
        self._resources: List[Resource] = []
        self._types: Set[str] = set()
        self._mark_type_names: Set[str] = set()
        self._version = "1.0.0"

        logger.info("ResourceManager initialized")

    def load(self) -> bool:
        """加载资源数据"""
        data = load_json(self._data_path, default={"resources": []})
        if data is None:
            return False

        self._version = data.get("version", "1.0.0")
        self._resources = []
        self._types = set()
        self._mark_type_names = set()

        for item in data.get("resources", []):
            try:
                res = Resource(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    type=item.get("type", ""),
                    x=float(item.get("x", item.get("position", {}).get("x", 0))),
                    y=float(item.get("y", item.get("position", {}).get("y", 0))),
                    map_id=item.get("map_id", "default"),
                    mark_type=int(item.get("mark_type", 0)),
                    mark_type_name=item.get("mark_type_name", ""),
                    icon_url=item.get("icon_url", ""),
                    description=item.get("description", ""),
                    source=item.get("source", "manual"),
                    last_updated=item.get("last_updated", ""),
                )
                self._resources.append(res)
                self._types.add(res.type)
                if res.mark_type_name:
                    self._mark_type_names.add(res.mark_type_name)
            except Exception as e:
                logger.warning("Failed to parse resource: %s", e)

        logger.info("Loaded %d resources (%d types, %d mark_type_names)",
                     len(self._resources), len(self._types), len(self._mark_type_names))
        return True

    def save(self) -> bool:
        """保存资源数据"""
        data = {
            "version": self._version,
            "last_updated": datetime.now().isoformat(),
            "source": "mixed",
            "resources": [
                {
                    "id": r.id, "name": r.name, "type": r.type,
                    "x": r.x, "y": r.y, "map_id": r.map_id,
                    "mark_type": r.mark_type, "mark_type_name": r.mark_type_name,
                    "icon_url": r.icon_url,
                    "description": r.description, "source": r.source,
                    "last_updated": r.last_updated,
                }
                for r in self._resources
            ]
        }
        return save_json(self._data_path, data)

    # ==================== 查询 ====================

    def get_all(self) -> List[Resource]:
        return self._resources.copy()

    def get_by_type(self, resource_type: str) -> List[Resource]:
        return [r for r in self._resources if r.type == resource_type]

    def get_by_map(self, map_id: str) -> List[Resource]:
        return [r for r in self._resources if r.map_id == map_id]

    def get_by_id(self, resource_id: str) -> Optional[Resource]:
        for r in self._resources:
            if r.id == resource_id:
                return r
        return None

    def search(self, keyword: str) -> List[Resource]:
        keyword = keyword.lower()
        return [r for r in self._resources
                if keyword in r.name.lower() or keyword in r.description.lower()]

    def get_types(self) -> List[str]:
        return sorted(self._types)

    def get_mark_type_names(self) -> List[str]:
        """获取所有细分类名（排序后）"""
        return sorted(self._mark_type_names)

    def get_mark_type_names_by_type(self) -> Dict[str, List[str]]:
        """Get mark_type_names organized by parent type category.
        Skips resources with empty type or mark_type_name.
        """
        result: Dict[str, set] = {}
        for r in self._resources:
            if not r.type or not r.mark_type_name:
                continue
            if r.type not in result:
                result[r.type] = set()
            result[r.type].add(r.mark_type_name)
        return {k: sorted(v) for k, v in sorted(result.items())}

    def get_point_counts_by_mark_type_name(self) -> Dict[str, int]:
        """获取每种 mark_type_name 的点位数量"""
        counts: Dict[str, int] = {}
        for r in self._resources:
            if r.mark_type_name:
                counts[r.mark_type_name] = counts.get(r.mark_type_name, 0) + 1
        return counts

    def get_nearby(self, x: float, y: float, radius: float,
                   map_id: Optional[str] = None) -> List[Resource]:
        """获取指定位置附近的资源点"""
        results = []
        for r in self._resources:
            if map_id and r.map_id != map_id:
                continue
            dist = ((r.x - x) ** 2 + (r.y - y) ** 2) ** 0.5
            if dist <= radius:
                results.append(r)
        return results

    # ==================== 增删改 ====================

    def add(self, resource: Resource) -> bool:
        if self.get_by_id(resource.id):
            logger.warning("Resource ID already exists: %s", resource.id)
            return False
        self._resources.append(resource)
        self._types.add(resource.type)
        if resource.mark_type_name:
            self._mark_type_names.add(resource.mark_type_name)
        return True

    def _rebuild_indexes(self):
        """重建类型索引，确保更新/删除后筛选项与资源列表一致。"""
        self._types = {r.type for r in self._resources}
        self._mark_type_names = {
            r.mark_type_name for r in self._resources if r.mark_type_name
        }

    def update(self, resource: Resource) -> bool:
        for i, r in enumerate(self._resources):
            if r.id == resource.id:
                self._resources[i] = resource
                self._rebuild_indexes()
                return True
        return False

    def delete(self, resource_id: str) -> bool:
        for i, r in enumerate(self._resources):
            if r.id == resource_id:
                self._resources.pop(i)
                self._rebuild_indexes()
                return True
        return False

    def clear(self):
        self._resources.clear()
        self._types.clear()
        self._mark_type_names.clear()

    # ==================== 转换为 MapCanvas 格式 ====================

    def to_display_list(self, map_id: Optional[str] = None,
                        type_filter: Optional[str] = None,
                        mark_type_names=None) -> List[dict]:
        """转换为 MapCanvas 可用的 dict 列表

        Args:
            map_id: filter by map_id
            type_filter: filter by broad type category
            mark_type_names: a set/list of mark_type_name strings to include
        """
        results = []
        for r in self._resources:
            if map_id and r.map_id != map_id:
                continue
            if type_filter and r.type != type_filter:
                continue
            if mark_type_names and r.mark_type_name not in mark_type_names:
                continue
            results.append({
                "x": r.x, "y": r.y,
                "name": r.name, "type": r.type,
                "id": r.id, "mark_type": r.mark_type,
                "mark_type_name": r.mark_type_name,
            })
        return results

    @property
    def count(self) -> int:
        return len(self._resources)
