"""ADC-002 — gắn ước tính thời lượng vào work order (nhóm sản phẩm theo từ khóa, BR-02)."""

from src.modules.intake import WorkOrder, apply_estimate, try_estimate

SPEC_EXAMPLE = {
    "product_name": "Bột ớt xay khô",
    "quantity": 120,
    "pkg_length_cm": 40,
    "pkg_width_cm": 30,
    "pkg_height_cm": 25,
    "pkg_weight_kg": 8,
    "required_dose_kgy": 10,
}


def test_apply_estimate_stores_group_duration_breakdown_and_version(config):
    wo = WorkOrder(**SPEC_EXAMPLE)
    assert apply_estimate(wo, config) is None
    assert (wo.product_group, wo.estimated_duration_min, wo.config_version) == ("spice", 180, config.version)
    assert wo.estimate_breakdown == {
        "setup": 30,
        "weight_load": 48,
        "volume_load": 36,
        "dose_load": 42,
        "buffer": 15.6,
    }


def test_unknown_product_is_not_estimated(config):
    wo = WorkOrder(**{**SPEC_EXAMPLE, "product_name": "Hạt điều rang muối"})
    reason = apply_estimate(wo, config)
    assert "nhóm sản phẩm" in reason
    assert (wo.product_group, wo.estimated_duration_min, wo.estimate_breakdown) == (None, None, None)


def test_group_with_unconfigured_factor_reports_config_error(config):
    # seafood còn null trong throughput.yaml → lỗi, không lấy mặc định (BR-02)
    reason = try_estimate(WorkOrder(**{**SPEC_EXAMPLE, "product_name": "Tôm sú đông lạnh"}), config)
    assert isinstance(reason, str) and "seafood" in reason


def test_missing_field_is_not_estimated(config):
    assert try_estimate(WorkOrder(**{**SPEC_EXAMPLE, "quantity": None}), config) == "thiếu trường để ước tính"


def test_reapply_clears_stale_estimate(config):
    wo = WorkOrder(**SPEC_EXAMPLE)
    apply_estimate(wo, config)
    wo.required_dose_kgy = 25  # TODO trong cấu hình
    assert apply_estimate(wo, config) is not None
    assert (wo.estimated_duration_min, wo.config_version) == (None, None)
