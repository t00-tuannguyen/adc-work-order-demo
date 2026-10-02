"""Đọc và kiểm tra file giả định throughput (src/config/throughput.yaml).

File sai định dạng hoặc thiếu key → ConfigError, app không khởi động (ADC-002).
Giá trị `null` (TODO chưa chốt) được giữ nguyên; chỉ báo lỗi khi thực sự dùng tới (BR-02).
Đổi file khi app đang chạy → `ThroughputConfigSource` tự nạp lại; file mới sai → giữ bản cũ, ghi log lỗi (T-023).
"""

import logging
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path

import yaml

from src.modules.scheduling.scheduler import ShiftPolicy

logger = logging.getLogger(__name__)

REQUIRED_KEYS = (
    "version",
    "setup_min",
    "min_per_kg",
    "min_per_m3",
    "buffer_pct",
    "round_to_min",
    "density_factor",
    "dose_factor",
)


class ConfigError(ValueError):
    """File cấu hình throughput không hợp lệ."""


@dataclass(frozen=True)
class ThroughputConfig:
    version: str
    setup_min: float
    min_per_kg: float
    min_per_m3: float
    buffer_pct: float
    round_to_min: int
    density_factor: dict[str, float | None]
    dose_factor: dict[str, float | None]
    raw: dict
    # Nhóm sản phẩm → từ khóa trong tên sản phẩm (đã chuẩn hóa chữ thường); thứ tự theo file
    product_groups: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "ThroughputConfig":
        if not isinstance(data, dict):
            raise ConfigError("throughput config phải là mapping YAML")
        missing = [k for k in REQUIRED_KEYS if k not in data]
        if missing:
            raise ConfigError(f"throughput config thiếu key: {', '.join(missing)}")
        for key in ("setup_min", "min_per_kg", "min_per_m3", "buffer_pct", "round_to_min"):
            value = data[key]
            if not isinstance(value, int | float) or value < 0:
                raise ConfigError(f"'{key}' phải là số ≥ 0, nhận {value!r}")
        if data["round_to_min"] <= 0:
            raise ConfigError("'round_to_min' phải > 0")
        for key in ("density_factor", "dose_factor"):
            if not isinstance(data[key], dict) or not data[key]:
                raise ConfigError(f"'{key}' phải là mapping không rỗng")
        product_groups = _product_groups(data.get("product_groups") or {}, data["density_factor"])
        try:  # ca làm của line (ADC-003, T-054) — kiểm tra ngay để file sai không lọt qua lúc nạp lại
            ShiftPolicy.from_config(data, UTC)
        except ValueError as e:
            raise ConfigError(str(e)) from e
        return cls(
            version=str(data["version"]),
            setup_min=float(data["setup_min"]),
            min_per_kg=float(data["min_per_kg"]),
            min_per_m3=float(data["min_per_m3"]),
            buffer_pct=float(data["buffer_pct"]),
            round_to_min=int(data["round_to_min"]),
            density_factor={str(k): v for k, v in data["density_factor"].items()},
            dose_factor={str(k): v for k, v in data["dose_factor"].items()},
            raw=data,
            product_groups=product_groups,
        )

    def classify_product(self, product_name: str | None) -> str | None:
        """Tên sản phẩm → nhóm trong `density_factor` theo bảng từ khóa.

        Không khớp nhóm nào, hoặc khớp nhiều nhóm → None (không đoán; ước tính sẽ báo lỗi — BR-02).
        """
        if not product_name:
            return None
        name = _normalize(product_name)
        matched = [g for g, words in self.product_groups.items() if any(w in name for w in words)]
        return matched[0] if len(matched) == 1 else None


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold().strip()


def _product_groups(data: object, density_factor: dict) -> dict[str, tuple[str, ...]]:
    if not isinstance(data, dict):
        raise ConfigError("'product_groups' phải là mapping nhóm → danh sách từ khóa")
    out: dict[str, tuple[str, ...]] = {}
    for group, words in data.items():
        if group not in density_factor:
            raise ConfigError(f"product_groups '{group}' không có trong density_factor")
        if not isinstance(words, list) or not words or not all(isinstance(w, str) and w.strip() for w in words):
            raise ConfigError(f"product_groups '{group}' phải là danh sách từ khóa không rỗng")
        out[str(group)] = tuple(_normalize(w) for w in words)
    return out


def load_config(path: str | Path) -> ThroughputConfig:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"không đọc được {path}: {e}") from e
    return ThroughputConfig.from_dict(data)


class ThroughputConfigSource:
    """Giữ cấu hình đang dùng, nạp lại khi file đổi (so mtime).

    Lần nạp đầu lỗi → ConfigError (app không khởi động). Các lần sau lỗi → giữ bản cũ + log lỗi,
    để một lần sửa file dở dang không làm sập app đang chạy demo.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._config: ThroughputConfig | None = None

    def get(self) -> ThroughputConfig:
        with self._lock:
            try:
                mtime = self.path.stat().st_mtime
            except OSError as e:
                if self._config is None:
                    raise ConfigError(f"không đọc được {self.path}: {e}") from e
                logger.error("Không đọc được %s, giữ cấu hình %s: %s", self.path, self._config.version, e)
                return self._config
            if self._config is not None and mtime == self._mtime:
                return self._config
            try:
                config = load_config(self.path)
            except ConfigError:
                if self._config is None:
                    raise
                logger.exception("Cấu hình throughput mới không hợp lệ, giữ bản %s", self._config.version)
                self._mtime = mtime  # không thử lại cho tới lần sửa file kế tiếp
                return self._config
            if self._config is not None:
                logger.info("Nạp lại cấu hình throughput %s → %s", self._config.version, config.version)
            self._config, self._mtime = config, mtime
            return config
