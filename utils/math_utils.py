"""
数学计算工具

提供导航和位置计算相关的数学函数。
"""

import math
from typing import Tuple, List, Optional
from dataclasses import dataclass


@dataclass
class Point:
    """二维点"""
    x: float
    y: float


@dataclass
class Rect:
    """矩形区域"""
    x: int
    y: int
    width: int
    height: int
    
    @property
    def center(self) -> Point:
        """矩形中心点"""
        return Point(self.x + self.width / 2, self.y + self.height / 2)
    
    @property
    def right(self) -> int:
        return self.x + self.width
    
    @property
    def bottom(self) -> int:
        return self.y + self.height


def distance(p1: Point, p2: Point) -> float:
    """
    计算两点之间的欧几里得距离
    
    Args:
        p1: 点1
        p2: 点2
        
    Returns:
        float: 距离
    """
    return math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2)


def direction_angle(from_point: Point, to_point: Point) -> float:
    """
    计算从一个点到另一个点的方向角（度）
    0度为正北（向上），顺时针增加
    
    Args:
        from_point: 起点
        to_point: 终点
        
    Returns:
        float: 方向角 (0-360度)
    """
    dx = to_point.x - from_point.x
    dy = to_point.y - from_point.y
    
    # atan2 返回 (-pi, pi), 以 x 轴正方向为 0
    # 转换为以 y 轴负方向(正北)为 0，顺时针
    angle = math.degrees(math.atan2(dx, -dy))
    
    # 确保在 0-360 范围内
    if angle < 0:
        angle += 360
    
    return angle


def direction_text(angle: float) -> str:
    """
    将角度转换为方向文字
    
    Args:
        angle: 方向角 (0-360度)
        
    Returns:
        str: 方向文字（如 "北", "东北", "东" 等）
    """
    directions = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    index = round(angle / 45) % 8
    return directions[index]


def calculate_eta(distance_val: float, speed: float = 5.0) -> float:
    """
    计算预计到达时间
    
    Args:
        distance_val: 距离
        speed: 移动速度 (像素/秒)
        
    Returns:
        float: 预计到达时间 (秒)
    """
    if speed <= 0:
        return float("inf")
    return distance_val / speed


def total_route_distance(points: List[Point]) -> float:
    """
    计算路线总距离
    
    Args:
        points: 路线点列表
        
    Returns:
        float: 总距离
    """
    if len(points) < 2:
        return 0.0
    
    total = 0.0
    for i in range(len(points) - 1):
        total += distance(points[i], points[i + 1])
    return total


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    将值限制在范围内
    
    Args:
        value: 输入值
        min_val: 最小值
        max_val: 最大值
        
    Returns:
        float: 限制后的值
    """
    return max(min_val, min(max_val, value))


def lerp(a: float, b: float, t: float) -> float:
    """
    线性插值
    
    Args:
        a: 起始值
        b: 结束值
        t: 插值参数 (0-1)
        
    Returns:
        float: 插值结果
    """
    return a + (b - a) * clamp(t, 0.0, 1.0)


def point_in_rect(point: Point, rect: Rect) -> bool:
    """
    判断点是否在矩形内
    
    Args:
        point: 点
        rect: 矩形
        
    Returns:
        bool: 是否在矩形内
    """
    return (rect.x <= point.x <= rect.x + rect.width and
            rect.y <= point.y <= rect.y + rect.height)


def normalize_angle(angle: float) -> float:
    """
    将角度规范化到 0-360 范围
    
    Args:
        angle: 输入角度
        
    Returns:
        float: 规范化后的角度
    """
    angle = angle % 360
    if angle < 0:
        angle += 360
    return angle
