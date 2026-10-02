"""ADC-001 — cổng HITL theo độ tin cậy sau OCR (TC2, TC11–TC14), ADR-0007, BR-12, BR-13."""

import pytest

from src.modules.intake import (
    FieldSignal,
    FlagCode,
    IntakeFlag,
    ReviewDecision,
    ReviewThresholds,
    SourceKind,
    TicketSignal,
    assess,
)

T = ReviewThresholds(low=0.8, warn=0.9)
CLEAR = {
    "product_name": FieldSignal(SourceKind.VERBATIM, 0.97),
    "quantity": FieldSignal(SourceKind.VERBATIM, 0.95),
    "pkg_weight_kg": FieldSignal(SourceKind.CONVERTED, None),
}


def test_high_confidence_is_auto_without_hitl():
    result = assess(CLEAR, T)
    assert result.decision == ReviewDecision.AUTO
    assert result.flags == []


def test_no_signals_means_text_layer_or_manual_and_is_auto():
    assert assess({}, T).decision == ReviewDecision.AUTO


@pytest.mark.parametrize("signal", [FieldSignal(SourceKind.VERBATIM, 0.79), FieldSignal(SourceKind.OCR_LOW, None)])
def test_low_confidence_requires_review(signal):
    result = assess({**CLEAR, "quantity": signal}, T)
    assert result.decision == ReviewDecision.REVIEW
    assert result.review_flags == [IntakeFlag(FlagCode.LOW_CONFIDENCE, "quantity")]


def test_gray_zone_warns_but_does_not_block():
    result = assess({**CLEAR, "quantity": FieldSignal(SourceKind.VERBATIM, 0.8)}, T)
    assert result.decision == ReviewDecision.WARN
    assert result.warnings == [IntakeFlag(FlagCode.AMBIGUOUS_OCR, "quantity")]


@pytest.mark.parametrize(
    ("kind", "code"),
    [(SourceKind.INFERRED, FlagCode.INFERRED_VALUE), (SourceKind.DEFAULT, FlagCode.DEFAULT_VALUE)],
)
def test_inferred_or_default_value_warns(kind, code):
    result = assess({**CLEAR, "priority": FieldSignal(kind, None)}, T)
    assert result.decision == ReviewDecision.WARN
    assert result.warnings == [IntakeFlag(code, "priority")]


def test_review_wins_over_warning_and_keeps_all_flags():
    signals = {**CLEAR, "quantity": FieldSignal(SourceKind.VERBATIM, 0.5), "priority": FieldSignal(SourceKind.INFERRED)}
    result = assess(signals, T)
    assert result.decision == ReviewDecision.REVIEW
    assert {f.code for f in result.flags} == {FlagCode.LOW_CONFIDENCE, FlagCode.INFERRED_VALUE}


def test_manual_field_is_trusted_after_human_confirms():
    result = assess({**CLEAR, "quantity": FieldSignal(SourceKind.MANUAL, 0.3)}, T)
    assert result.decision == ReviewDecision.AUTO


def test_ticket_level_signals():
    assert assess(CLEAR, T, TicketSignal(boundary_uncertain=True)).decision == ReviewDecision.REVIEW
    dup = assess(CLEAR, T, TicketSignal(possible_duplicate=True))
    assert dup.decision == ReviewDecision.WARN
    assert dup.warnings == [IntakeFlag(FlagCode.POSSIBLE_DUPLICATE)]


def test_thresholds_from_config(config):
    assert ReviewThresholds.from_config(config.raw) == ReviewThresholds(low=0.8, warn=0.9)


def test_thresholds_must_be_ordered():
    with pytest.raises(ValueError):
        ReviewThresholds(low=0.9, warn=0.8)
