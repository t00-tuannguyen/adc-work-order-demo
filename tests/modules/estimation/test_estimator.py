"""ADC-002 — Kế hoạch kiểm thử."""

import dataclasses

import pytest

from src.modules.estimation import ConfigError, EstimateInput, EstimationError, ThroughputConfig, estimate_duration

SPEC_EXAMPLE = EstimateInput(
    product_group="spice",
    quantity=120,
    pkg_length_cm=40,
    pkg_width_cm=30,
    pkg_height_cm=25,
    pkg_weight_kg=8,
    required_dose_kgy=10,
)


def test_spec_example_is_180_minutes(config):
    result = estimate_duration(SPEC_EXAMPLE, config)
    assert result.duration_min == 180
    b = result.breakdown
    assert (b.setup, b.weight_load, b.volume_load, b.dose_load, b.buffer) == (30, 48, 36, 42, 15.6)
    assert result.config_version == config.version


def test_same_input_100_runs_same_result(config):
    results = {estimate_duration(SPEC_EXAMPLE, config) for _ in range(100)}
    assert len(results) == 1


def test_higher_dose_factor_increases_dose_load_proportionally(config):
    raw = {**config.raw, "dose_factor": {"10": 2.0}}
    bigger = estimate_duration(SPEC_EXAMPLE, ThroughputConfig.from_dict(raw))
    base = estimate_duration(SPEC_EXAMPLE, config)
    # dose_load = (weight + volume) × (factor − 1): 1.0 / 0.5 = gấp đôi
    assert bigger.breakdown.dose_load == pytest.approx(base.breakdown.dose_load * 2)
    assert bigger.duration_min > base.duration_min


def test_missing_config_key_raises(config):
    raw = {k: v for k, v in config.raw.items() if k != "min_per_kg"}
    with pytest.raises(ConfigError, match="min_per_kg"):
        ThroughputConfig.from_dict(raw)


@pytest.mark.parametrize(
    "change",
    [
        {"product_group": "unknown"},  # không có trong cấu hình
        {"product_group": "seafood"},  # có key nhưng còn TODO (null)
        {"required_dose_kgy": 7},
        {"required_dose_kgy": 5},  # TODO (null)
    ],
)
def test_unconfigured_factor_is_error_not_default(config, change):
    with pytest.raises(EstimationError):
        estimate_duration(dataclasses.replace(SPEC_EXAMPLE, **change), config)


@pytest.mark.parametrize("change", [{"quantity": 0}, {"quantity": -1}, {"pkg_weight_kg": 0}])
def test_non_positive_input_rejected(config, change):
    with pytest.raises(EstimationError):
        estimate_duration(dataclasses.replace(SPEC_EXAMPLE, **change), config)


def test_demo_random_estimate_between_4_and_8_hours(config, monkeypatch):
    from src.settings import get_settings

    monkeypatch.setenv("FEATURE_RANDOM_ESTIMATE", "true")
    get_settings.cache_clear()
    # liều 25 kGy chưa cấu hình — chế độ demo vẫn trả ước tính
    order = dataclasses.replace(SPEC_EXAMPLE, required_dose_kgy=25)
    results = [estimate_duration(order, config) for _ in range(200)]
    for r in results:
        assert 240 <= r.duration_min <= 480
        assert r.duration_min % config.round_to_min == 0
        b = r.breakdown
        assert b.setup + b.weight_load + b.volume_load + b.dose_load + b.buffer == pytest.approx(
            r.duration_min, abs=0.02
        )
        assert r.config_version == f"{config.version}-demo-random"
    assert len({r.duration_min for r in results}) > 1


def test_demo_random_still_rejects_invalid_quantity(config, monkeypatch):
    from src.settings import get_settings

    monkeypatch.setenv("FEATURE_RANDOM_ESTIMATE", "true")
    get_settings.cache_clear()
    with pytest.raises(EstimationError):
        estimate_duration(dataclasses.replace(SPEC_EXAMPLE, quantity=0), config)
