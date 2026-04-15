"""
WIKI 数据更新器

从洛克王国 WIKI 获取:
1. 地图瓦片 -> 拼接为完整地图
2. 标记类型数据 (markType)
3. 点位坐标数据 (point.json)
4. 图标资源
"""

import logging
import os
import re
import json
import time
import math
from typing import Optional, Dict, List, Callable, Tuple
from datetime import datetime
from io import BytesIO

import cv2
import numpy as np
import requests
from bs4 import BeautifulSoup
from PIL import Image

from roco_navigator.utils.file_utils import (
    get_data_dir, get_assets_dir, save_json, load_json, ensure_dir, backup_file
)

logger = logging.getLogger(__name__)


class WikiUpdater:
    """
    WIKI 数据更新器

    功能:
    - download_map: 下载地图瓦片并拼接为完整地图图片
    - update_points: 获取点位标记类型 + 坐标数据
    - download_icons: 下载标记图标
    """

    WIKI_MAP_URL = "https://wiki.biligame.com/rocom/%E5%A4%A7%E5%9C%B0%E5%9B%BE"
    TILE_URL_TEMPLATE = "https://wiki-dev-patch-oss.oss-cn-hangzhou.aliyuncs.com/res/lkwg/map-3.0/{z}/tile-{x}_{y}.png"
    POINT_DATA_URL = "https://wiki.biligame.com/rocom/Data:Mapnew/point.json"

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # Tile grid bounds (tiles go from -bound to +bound on each axis)
    TILE_BOUND = 4

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

        self._cache_path = os.path.join(get_data_dir(), "wiki_cache.json")
        self._icons_dir = os.path.join(get_assets_dir(), "icons", "wiki")
        self._maps_dir = os.path.join(get_assets_dir(), "maps")
        self._update_in_progress = False

        ensure_dir(self._icons_dir)
        ensure_dir(self._maps_dir)
        logger.info("WikiUpdater initialized")

    # ==================== Map Download ====================

    def download_map(self, zoom: int = 6,
                     progress_callback: Optional[Callable] = None
                     ) -> Tuple[bool, str]:
        """
        Download map tiles and stitch into a complete map image.

        Uses Leaflet tile system:
        - URL pattern: /map-3.0/{z}/tile-{x}_{y}.png
        - Tile coordinates range from -TILE_BOUND to +TILE_BOUND

        Args:
            zoom: Zoom level (4-8, higher = more detail but larger file)
            progress_callback: (percent, message) callback

        Returns:
            (success, message)
        """
        if self._update_in_progress:
            return False, "Update already in progress"

        self._update_in_progress = True
        try:
            if progress_callback:
                progress_callback(0, f"Starting map download (zoom={zoom})...")

            bound = self.TILE_BOUND
            # Tile indices go from -bound to bound (inclusive)
            x_range = range(-bound, bound + 1)
            y_range = range(-bound, bound + 1)
            total_tiles = len(x_range) * len(y_range)

            # Download all tiles
            tiles = {}
            downloaded = 0
            failed = 0
            tile_size = None

            for yi, ty in enumerate(y_range):
                for xi, tx in enumerate(x_range):
                    url = self.TILE_URL_TEMPLATE.format(z=zoom, x=tx, y=ty)
                    try:
                        resp = self._session.get(url, timeout=10)
                        if resp.status_code == 200 and len(resp.content) > 100:
                            img = Image.open(BytesIO(resp.content))
                            tiles[(tx, ty)] = img
                            if tile_size is None:
                                tile_size = img.size  # (width, height)
                            downloaded += 1
                        else:
                            failed += 1
                    except Exception as e:
                        logger.debug("Failed to download tile (%d,%d): %s", tx, ty, e)
                        failed += 1

                    count = yi * len(x_range) + xi + 1
                    if progress_callback:
                        pct = int(80 * count / total_tiles)
                        progress_callback(pct, f"Downloading tiles... {count}/{total_tiles}")

                    time.sleep(0.05)  # Rate limiting

            if not tiles or tile_size is None:
                return False, f"No tiles downloaded (failed={failed})"

            logger.info("Downloaded %d tiles (%d failed), tile_size=%s",
                        downloaded, failed, tile_size)

            # Stitch tiles into a single image
            if progress_callback:
                progress_callback(85, "Stitching tiles...")

            tw, th = tile_size
            cols = len(x_range)
            rows = len(y_range)
            full_width = cols * tw
            full_height = rows * th

            full_map = Image.new("RGB", (full_width, full_height), (27, 34, 52))

            for (tx, ty), tile_img in tiles.items():
                # Convert tile coord to pixel position
                px = (tx - (-bound)) * tw
                py = (ty - (-bound)) * th
                full_map.paste(tile_img, (px, py))

            # Save as PNG
            if progress_callback:
                progress_callback(92, "Saving map image...")

            map_filename = f"world_map_z{zoom}.png"
            map_path = os.path.join(self._maps_dir, map_filename)
            full_map.save(map_path, "PNG")

            file_size_mb = os.path.getsize(map_path) / (1024 * 1024)

            if progress_callback:
                progress_callback(100, "Map download complete!")

            msg = (f"Map saved: {map_filename} ({full_width}x{full_height}, "
                   f"{file_size_mb:.1f}MB, {downloaded} tiles)")
            logger.info(msg)
            return True, msg

        except Exception as e:
            logger.error("Map download failed: %s", e)
            return False, f"Map download failed: {str(e)}"
        finally:
            self._update_in_progress = False

    # ==================== Points Update ====================

    def update_points(self, progress_callback: Optional[Callable] = None
                      ) -> Tuple[bool, str]:
        """
        Update point/marker data from WIKI.

        1. Fetch main page -> extract categoryData (markTypes)
        2. Fetch point.json -> extract point coordinates
        3. Download icons
        4. Save to cache

        Args:
            progress_callback: (percent, message) callback

        Returns:
            (success, message)
        """
        if self._update_in_progress:
            return False, "Update already in progress"

        self._update_in_progress = True
        try:
            # Step 1: Fetch main page for markType data
            if progress_callback:
                progress_callback(5, "Fetching WIKI page...")

            html = self._fetch_page(self.WIKI_MAP_URL)
            if html is None:
                return False, "Failed to fetch WIKI page"

            # Step 2: Parse categoryData
            if progress_callback:
                progress_callback(15, "Parsing mark types...")

            mark_types = self._parse_category_data(html)
            if not mark_types:
                logger.warning("categoryData parsing failed, trying JS fallback")
                mark_types = self._parse_mark_types_fallback(html)

            # Step 3: Fetch point coordinates
            if progress_callback:
                progress_callback(30, "Fetching point data...")

            points = self._fetch_point_data(html)

            # Step 4: Download icons
            if progress_callback:
                progress_callback(45, "Downloading icons...")

            icon_count = self._download_icons(mark_types, progress_callback)

            # Step 5: Save cache
            if progress_callback:
                progress_callback(90, "Saving data...")

            backup_file(self._cache_path)

            cache_data = {
                "last_fetch": datetime.now().isoformat(),
                "version": "2.0.0",
                "wiki_url": self.WIKI_MAP_URL,
                "mark_types": mark_types,
                "points": points,
                "total_types": len(mark_types),
                "total_points": len(points),
            }
            save_json(self._cache_path, cache_data)

            if progress_callback:
                progress_callback(100, "Points update complete!")

            msg = (f"Updated: {len(mark_types)} mark types, "
                   f"{len(points)} points, {icon_count} icons")
            logger.info(msg)
            return True, msg

        except Exception as e:
            logger.error("Points update failed: %s", e)
            return False, f"Update failed: {str(e)}"
        finally:
            self._update_in_progress = False

    # ==================== Internal: Fetch ====================

    def _fetch_page(self, url: str) -> Optional[str]:
        try:
            resp = self._session.get(url, timeout=20)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            logger.info("Fetched page: %s (%d bytes)", url, len(resp.text))
            return resp.text
        except requests.RequestException as e:
            logger.error("Failed to fetch: %s", e)
            return None

    # ==================== Internal: Parse ====================

    def _parse_category_data(self, html: str) -> List[Dict]:
        """Parse markType data from <div id="categoryData">"""
        mark_types = []
        try:
            soup = BeautifulSoup(html, "lxml")
            cat_div = soup.find("div", id="categoryData")
            if cat_div is None:
                logger.warning("categoryData div not found")
                return []

            text = cat_div.get_text(strip=True)
            data = json.loads(text)

            for item in data.get("data", []):
                mt = {
                    "mark_type": int(item.get("markType", 0)),
                    "mark_type_name": item.get("markTypeName", ""),
                    "type": item.get("type", ""),
                    "icon_url": item.get("icon", ""),
                    "length": int(item.get("length", 0)),
                    "default_show": item.get("defaultShow") in (True, "true", "1", ""),
                    "desc": item.get("desc", ""),
                }
                mark_types.append(mt)

            logger.info("Parsed %d mark types from categoryData", len(mark_types))
        except (json.JSONDecodeError, Exception) as e:
            logger.error("Failed to parse categoryData: %s", e)

        return mark_types

    def _parse_mark_types_fallback(self, html: str) -> List[Dict]:
        """Fallback: parse markType from script tags"""
        mark_types = []
        patterns = [
            r'markTypeList\s*[=:]\s*(\[.*?\])',
            r'"data"\s*:\s*(\[.*?"markType".*?\])',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    for item in data:
                        mark_types.append({
                            "mark_type": int(item.get("markType", 0)),
                            "mark_type_name": item.get("markTypeName", ""),
                            "type": item.get("type", ""),
                            "icon_url": item.get("icon", ""),
                            "length": int(item.get("length", 0)),
                            "default_show": False,
                        })
                    if mark_types:
                        return mark_types
                except (json.JSONDecodeError, Exception):
                    continue
        return mark_types

    def _fetch_point_data(self, html: str) -> List[Dict]:
        """
        Fetch point coordinate data.

        First try to find #mapPointData in the page HTML.
        If not found, fetch from Data:Mapnew/point.json wiki page.
        """
        points = []

        # Strategy 1: embedded in page
        try:
            soup = BeautifulSoup(html, "lxml")
            point_div = soup.find("div", id="mapPointData")
            if point_div:
                text = point_div.get_text(strip=True)
                data = json.loads(text)
                points = self._parse_points(data)
                if points:
                    logger.info("Parsed %d points from embedded data", len(points))
                    return points
        except Exception as e:
            logger.debug("Embedded point data not found: %s", e)

        # Strategy 2: fetch the wiki page for point.json
        try:
            resp = self._session.get(self.POINT_DATA_URL, timeout=15)
            if resp.status_code == 200:
                resp.encoding = "utf-8"
                page_html = resp.text
                soup2 = BeautifulSoup(page_html, "lxml")
                point_div2 = soup2.find("div", id="mapPointData")
                if point_div2:
                    text = point_div2.get_text(strip=True)
                    data = json.loads(text)
                    points = self._parse_points(data)
                    if points:
                        logger.info("Parsed %d points from point.json page", len(points))
                        return points
        except Exception as e:
            logger.debug("Failed to fetch point.json page: %s", e)

        # Strategy 3: use MediaWiki API
        try:
            api_url = "https://wiki.biligame.com/rocom/api.php"
            params = {
                "action": "query",
                "titles": "Data:Mapnew/point.json",
                "prop": "revisions",
                "rvprop": "content",
                "format": "json",
            }
            resp = self._session.get(api_url, params=params, timeout=15)
            if resp.status_code == 200:
                api_data = resp.json()
                pages = api_data.get("query", {}).get("pages", {})
                for page in pages.values():
                    revisions = page.get("revisions", [])
                    if revisions:
                        content = revisions[0].get("*", "")
                        # The content might have the data embedded in HTML
                        soup3 = BeautifulSoup(content, "lxml")
                        point_div3 = soup3.find("div", id="mapPointData")
                        if point_div3:
                            data = json.loads(point_div3.get_text(strip=True))
                            points = self._parse_points(data)
                            logger.info("Parsed %d points from API", len(points))
                            return points
        except Exception as e:
            logger.debug("API point fetch failed: %s", e)

        logger.warning("No point data could be fetched")
        return points

    def _parse_points(self, data) -> List[Dict]:
        """Parse point data from JSON structure"""
        points = []
        items = []

        if isinstance(data, dict):
            items = data.get("data", data.get("points", []))
        elif isinstance(data, list):
            items = data

        for item in items:
            try:
                point = {
                    "id": str(item.get("id", item.get("pointId", ""))),
                    "name": item.get("name", item.get("title", "")),
                    "mark_type": int(item.get("markType", item.get("mark_type", 0))),
                    "x": float(item.get("x", item.get("lng", 0))),
                    "y": float(item.get("y", item.get("lat", 0))),
                    "desc": item.get("desc", item.get("description", "")),
                }
                if point["id"]:
                    points.append(point)
            except (ValueError, TypeError):
                continue

        return points

    # ==================== Internal: Icons ====================

    def _download_icons(self, mark_types: List[Dict],
                        progress_callback: Optional[Callable] = None) -> int:
        downloaded = 0
        icons_with_url = [m for m in mark_types if m.get("icon_url")]
        total = len(icons_with_url)

        for i, mt in enumerate(icons_with_url):
            icon_url = mt["icon_url"]
            mt_id = mt.get("mark_type", i)
            name = mt.get("mark_type_name", str(mt_id))
            safe_name = re.sub(r'[^\w\u4e00-\u9fff]', '_', name)
            filename = f"{mt_id}_{safe_name}.png"
            filepath = os.path.join(self._icons_dir, filename)

            if os.path.exists(filepath):
                continue

            try:
                url = icon_url
                if url.startswith("//"):
                    url = "https:" + url
                resp = self._session.get(url, timeout=10)
                resp.raise_for_status()
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                downloaded += 1
                time.sleep(0.08)
            except Exception as e:
                logger.debug("Icon download failed for %s: %s", name, e)

            if progress_callback and total > 0:
                pct = 45 + int(40 * (i + 1) / total)
                progress_callback(pct, f"Icons... ({i+1}/{total})")

        logger.info("Downloaded %d new icons", downloaded)
        return downloaded

    # ==================== Query ====================

    def get_cached_data(self) -> Optional[dict]:
        return load_json(self._cache_path)

    def get_last_update_time(self) -> Optional[str]:
        cache = self.get_cached_data()
        return cache.get("last_fetch") if cache else None

    def check_needs_update(self, days: int = 7) -> bool:
        last = self.get_last_update_time()
        if not last:
            return True
        try:
            age = (datetime.now() - datetime.fromisoformat(last)).days
            return age >= days
        except (ValueError, TypeError):
            return True

    def get_map_path(self, zoom: int = 6) -> Optional[str]:
        """Get path to downloaded map image, if it exists."""
        path = os.path.join(self._maps_dir, f"world_map_z{zoom}.png")
        return path if os.path.exists(path) else None

    def get_available_maps(self) -> List[str]:
        """List available downloaded map files."""
        if not os.path.exists(self._maps_dir):
            return []
        return [f for f in os.listdir(self._maps_dir)
                if f.endswith(('.png', '.jpg'))]

    @property
    def is_updating(self) -> bool:
        return self._update_in_progress
