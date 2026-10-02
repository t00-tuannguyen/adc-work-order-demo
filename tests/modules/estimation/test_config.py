"""T-023 — file cấu hình throughput: bảng nhóm sản phẩm + nạp lại khi file đổi."""

import os

import pytest
import yaml

from src.modules.estimation import ConfigError, ThroughputConfig, ThroughputConfigSource


@pytest.mark.parametrize(
    ("name", "group"),
    [
        ("Bột ớt xay khô", "spice"),
        ("Hạt tiêu đen", "spice"),
        ("BỘT NGHỆ VÀNG", "spice"),
        ("tôm đông lạnh", "seafood"),
        ("Xoài sấy dẻo", "fruit"),
        ("dried mango slices", "fruit"),
        ("Dưa hấu túi 10kg", "fruit"),
        ("vật tư y tế (găng tay)", "medical_goods"),
        # Tên thật từ ticket nhập 03–04/10/2026
        ("Dịch chanh dây", "fruit"),
        ("Dưa lưới đông lạnh", "fruit"),
        ("Thanh long - khóm", "fruit"),
        ("Chuối Slice đông lạnh", "fruit"),
        ("Thịt càng ghẹ", "seafood"),
        ("Đùi ếch đông lạnh", "seafood"),
        ("Cá tra phi lê", "seafood"),
        ("Thịt Vụn Cá Ngừ", "seafood"),
        ("Frozen Yellowfin Tuna Loin Nogas", "seafood"),
        ("DRIED SQUID", "seafood"),
        ("Tôm tẩm bột đông lạnh (Shrimp Ball)", "seafood"),  # "tẩm bột" không khớp nhóm powder
        ("Nấm đông cô hạt lựu", "vegetable"),
        ("Bắp cải sấy", "vegetable"),
        ("Bột Cà gai leo", "powder"),
        ("Bột mì", "powder"),
        ("Bột tắm thảo mộc Dr Cell", "powder"),
        ("Nhộng tằm đông lạnh", None),
        ("Hạt điều rang muối", None),  # không có nhóm → không đoán
        ("", None),
        (None, None),
    ],
)
def test_classify_product_from_sample_names(config, name, group):
    assert config.classify_product(name) == group


def test_name_matching_two_groups_is_not_classified(config):
    assert config.classify_product("tôm tẩm gia vị") is None


def test_product_group_must_exist_in_density_factor(config):
    raw = {**config.raw, "product_groups": {"nuts": ["hạt điều"]}}
    with pytest.raises(ConfigError, match="nuts"):
        ThroughputConfig.from_dict(raw)


def test_product_group_keywords_must_be_non_empty_list(config):
    raw = {**config.raw, "product_groups": {"spice": []}}
    with pytest.raises(ConfigError, match="spice"):
        ThroughputConfig.from_dict(raw)


def _write(path, data, mtime):
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_source_reloads_when_file_changes(config, tmp_path):
    path = tmp_path / "throughput.yaml"
    _write(path, config.raw, 1_000)
    source = ThroughputConfigSource(path)
    assert source.get().setup_min == 30

    _write(path, {**config.raw, "version": "0.2.0", "setup_min": 45}, 2_000)
    reloaded = source.get()
    assert (reloaded.version, reloaded.setup_min) == ("0.2.0", 45)


def test_source_keeps_last_good_config_when_new_file_invalid(config, tmp_path, caplog):
    path = tmp_path / "throughput.yaml"
    _write(path, config.raw, 1_000)
    source = ThroughputConfigSource(path)
    first = source.get()

    _write(path, {k: v for k, v in config.raw.items() if k != "min_per_kg"}, 2_000)
    assert source.get() is first
    assert "không hợp lệ" in caplog.text


def test_source_invalid_on_first_load_raises(tmp_path):
    path = tmp_path / "throughput.yaml"
    path.write_text("setup_min: [", encoding="utf-8")
    with pytest.raises(ConfigError):
        ThroughputConfigSource(path).get()


def test_source_missing_file_on_first_load_raises(tmp_path):
    with pytest.raises(ConfigError):
        ThroughputConfigSource(tmp_path / "missing.yaml").get()
