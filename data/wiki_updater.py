"""
WIKI 数据更新器

从洛克王国 WIKI (https://wiki.biligame.com/rocom/) 获取地图和资源数据。
支持一键更新、增量更新、图标下载。
"""

import logging
import os
import re
import json
import time
from typing import Optional, Dict, List, Callable, Tuple
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from roco_navigator.utils.file_utils import (
    get_data_dir, get_assets_dir, save_json, load_json, ensure_dir, backup_file
)

logger = logging.getLogger(__name__)


class WikiUpdater:
    """
    WIKI 数据更新器

    从 wiki.biligame.com 获取洛克王国地图数据。

    功能:
    - 获取地图标记类型数据
    - 下载资源图标
    - 增量更新
    - 数据验证
    """

    WIKI_MAP_URL = "https://wiki.biligame.com/rocom/%E5%A4%A7%E5%9C%B0%E5%9B%BE"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

        self._cache_path = os.path.join(get_data_dir(), "wiki_cache.json")
        self._icons_dir = os.path.join(get_assets_dir(), "icons", "wiki")
        self._update_in_progress = False

        ensure_dir(self._icons_dir)
        logger.info("WikiUpdater initialized")

    # ==================== 一键更新 ====================

    def one_click_update(self, progress_callback: Optional[Callable] = None
                         ) -> Tuple[bool, str]:
        """
        一键更新所有数据

        Steps:
        1. 获取 WIKI 页面数据
        2. 解析标记类型
        3. 下载图标
        4. 保存缓存

        Args:
            progress_callback: 进度回调 (percent: int, message: str)

        Returns:
            (success: bool, message: str)
        """
        if self._update_in_progress:
            return False, "Update already in progress"

        self._update_in_progress = True

        try:
            # Step 1: 获取页面
            if progress_callback:
                progress_callback(5, "Fetching WIKI page...")

            html = self._fetch_page(self.WIKI_MAP_URL)
            if html is None:
                return False, "Failed to fetch WIKI page"

            # Step 2: 解析数据
            if progress_callback:
                progress_callback(20, "Parsing map data...")

            mark_types = self._parse_map_data(html)
            if not mark_types:
                return False, "Failed to parse map data"

            # Step 3: 下载图标
            if progress_callback:
                progress_callback(40, "Downloading icons...")

            icon_count = self._download_icons(mark_types, progress_callback)

            # Step 4: 保存缓存
            if progress_callback:
                progress_callback(85, "Saving data...")

            # 备份旧缓存
            backup_file(self._cache_path)

            cache_data = {
                "last_fetch": datetime.now().isoformat(),
                "version": "1.0.0",
                "wiki_url": self.WIKI_MAP_URL,
                "mark_types": mark_types,
                "total_types": len(mark_types),
            }
            save_json(self._cache_path, cache_data)

            if progress_callback:
                progress_callback(100, "Update complete!")

            msg = f"Updated: {len(mark_types)} mark types, {icon_count} icons downloaded"
            logger.info(msg)
            return True, msg

        except Exception as e:
            logger.error("Update failed: %s", e)
            return False, f"Update failed: {str(e)}"
        finally:
            self._update_in_progress = False

    # ==================== 数据获取 ====================

    def _fetch_page(self, url: str) -> Optional[str]:
        """获取页面 HTML"""
        try:
            response = self._session.get(url, timeout=15)
            response.raise_for_status()
            response.encoding = "utf-8"
            logger.info("Fetched page: %s (%d bytes)", url, len(response.text))
            return response.text
        except requests.RequestException as e:
            logger.error("Failed to fetch page: %s", e)
            return None

    def _parse_map_data(self, html: str) -> List[Dict]:
        """
        解析 WIKI 页面中的地图数据

        WIKI 页面中嵌入了 JavaScript 数据，格式类似:
        markTypeList 或类似的 JSON 数据结构。

        Args:
            html: 页面 HTML

        Returns:
            标记类型列表
        """
        mark_types = []

        try:
            soup = BeautifulSoup(html, "lxml")

            # 尝试多种解析策略
            # 策略1: 查找嵌入的 JavaScript 数据
            scripts = soup.find_all("script")
            for script in scripts:
                text = script.string or ""

                # 查找 markTypeList 或类似数据
                patterns = [
                    r'markTypeList\s*[=:]\s*(\[.*?\])',
                    r'"markType"\s*:\s*(\[.*?\])',
                    r'var\s+\w+\s*=\s*(\[\s*\{.*?"markType".*?\}\s*\])',
                ]

                for pattern in patterns:
                    match = re.search(pattern, text, re.DOTALL)
                    if match:
                        try:
                            data = json.loads(match.group(1))
                            if isinstance(data, list) and data:
                                for item in data:
                                    mt = self._parse_mark_type(item)
                                    if mt:
                                        mark_types.append(mt)
                                if mark_types:
                                    logger.info("Parsed %d mark types from JS data",
                                                len(mark_types))
                                    return mark_types
                        except json.JSONDecodeError:
                            continue

            # 策略2: 查找页面中的表格数据
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows[1:]:  # 跳过表头
                    cols = row.find_all("td")
                    if len(cols) >= 3:
                        try:
                            name = cols[0].get_text(strip=True)
                            type_str = cols[1].get_text(strip=True) if len(cols) > 1 else ""
                            icon_img = cols[0].find("img")
                            icon_url = icon_img.get("src", "") if icon_img else ""

                            if name:
                                mark_types.append({
                                    "mark_type_name": name,
                                    "type": type_str,
                                    "icon_url": icon_url,
                                    "source": "wiki_table",
                                })
                        except Exception:
                            continue

            if mark_types:
                logger.info("Parsed %d mark types from table data", len(mark_types))
            else:
                logger.warning("No mark types found in page")

        except Exception as e:
            logger.error("Parse error: %s", e)

        return mark_types

    def _parse_mark_type(self, item: dict) -> Optional[dict]:
        """解析单个标记类型"""
        try:
            return {
                "mark_type": item.get("markType", item.get("mark_type", 0)),
                "mark_type_name": item.get("markTypeName", item.get("name", "")),
                "type": item.get("type", ""),
                "icon_url": item.get("icon", item.get("icon_url", "")),
                "length": int(item.get("length", 0)),
                "default_show": item.get("defaultShow") in (True, "true", "1"),
            }
        except Exception:
            return None

    # ==================== 图标下载 ====================

    def _download_icons(self, mark_types: List[Dict],
                        progress_callback: Optional[Callable] = None) -> int:
        """下载标记类型图标"""
        downloaded = 0
        total = len([m for m in mark_types if m.get("icon_url")])

        for i, mt in enumerate(mark_types):
            icon_url = mt.get("icon_url", "")
            if not icon_url:
                continue

            # 文件名
            mt_id = mt.get("mark_type", i)
            name = mt.get("mark_type_name", str(mt_id))
            # 安全文件名
            safe_name = re.sub(r'[^\w\u4e00-\u9fff]', '_', name)
            filename = f"{mt_id}_{safe_name}.png"
            filepath = os.path.join(self._icons_dir, filename)

            # 跳过已存在的
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
                time.sleep(0.1)  # 限速

            except Exception as e:
                logger.debug("Failed to download icon for %s: %s", name, e)

            if progress_callback and total > 0:
                pct = 40 + int(45 * (i + 1) / total)
                progress_callback(pct, f"Downloading icons... ({i+1}/{total})")

        logger.info("Downloaded %d new icons", downloaded)
        return downloaded

    # ==================== 查询 ====================

    def get_cached_data(self) -> Optional[dict]:
        """获取缓存的数据"""
        return load_json(self._cache_path)

    def get_last_update_time(self) -> Optional[str]:
        """获取上次更新时间"""
        cache = self.get_cached_data()
        if cache:
            return cache.get("last_fetch")
        return None

    def check_needs_update(self, days: int = 7) -> bool:
        """检查是否需要更新"""
        last = self.get_last_update_time()
        if not last:
            return True

        try:
            last_dt = datetime.fromisoformat(last)
            age = (datetime.now() - last_dt).days
            return age >= days
        except (ValueError, TypeError):
            return True

    @property
    def is_updating(self) -> bool:
        return self._update_in_progress
