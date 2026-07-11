from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, field

@dataclass
class VehicleConfig:
    """车辆配置类"""
    implement_width_m: float = 3.0
    overlap_ratio: float = 0.1
    path_inset_m: float = 1.0
    pivot_turn: bool = True
    yaw_rate_max_deg_s: float = 60.0
    min_turn_radius_m: Optional[float] = None
    work_min_turn_radius_m: Optional[float] = None
    work_max_curvature_rate_1pm2: Optional[float] = None
    pivot_radius_m: Optional[float] = None

    @property
    def effective_row_spacing(self) -> float:
        """有效行距（考虑重叠率）"""
        return self.implement_width_m * (1.0 - self.overlap_ratio)

    @property
    def effective_work_min_turn_radius_m(self) -> float:
        """Forward-only radius used while the implement remains engaged."""
        if self.work_min_turn_radius_m is not None:
            return float(self.work_min_turn_radius_m)
        if self.min_turn_radius_m is not None:
            return float(self.min_turn_radius_m)
        return max(1.0, self.implement_width_m * 0.75)

    @classmethod
    def from_dict(cls, data: Dict) -> 'VehicleConfig':
        """从字典创建实例，忽略未知字段"""
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

@dataclass
class ParcelData:
    """地块数据类"""
    outer: List[Tuple[float, float]]
    holes: List[List[Tuple[float, float]]] = field(default_factory=list)
    points: List[Tuple[float, float, float]] = field(default_factory=list)  # (lon, lat, diameter)
    entries: List[Dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> 'ParcelData':
        """从字典创建实例"""
        return cls(
            outer=[tuple(p) for p in data.get('outer', [])],
            holes=[[tuple(p) for p in h] for h in data.get('holes', [])],
            points=[tuple(p) for p in data.get('points', [])],
            entries=data.get('entries', [])
        )

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'outer': self.outer,
            'holes': self.holes,
            'points': self.points,
            'entries': self.entries
        }
