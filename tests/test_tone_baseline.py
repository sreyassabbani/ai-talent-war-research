"""Offline tests for the deterministic tone layer and baseline adjustment."""

from __future__ import annotations

from tag_edgar.baseline import BaselineConfig, apply_baselines, compute_family_baselines
from tag_edgar.tone import (
    LEXICONS,
    deal_tone_summary,
    lexicon_counts,
    lexicon_rates,
    passage_tone_rows,
    token_count,
)

MERGER_CLAUSE = (
    "The Company shall pay each Employee a retention bonus, and all unvested stock options "
    "will vest upon a change in control; severance benefits apply following termination "
    "without cause. Employees may continue benefits during the protective period."
)
PRESS_LINE = "We are excited to welcome the talented team and support future growth."


def test_token_count() -> None:
    assert token_count("Employees will vest.") == 3


def test_lexicon_counts_and_rates() -> None:
    counts = lexicon_counts(MERGER_CLAUSE)
    assert counts["retention"] >= 1
    assert counts["equity_vesting"] >= 1
    assert counts["protection_program"] >= 2
    rates = lexicon_rates(MERGER_CLAUSE)
    for name in LEXICONS:
        assert 0.0 <= rates[name] <= 100.0
    assert rates["modality"] > rates["hedging"]


def test_empty_text_rates_are_zero() -> None:
    rates = lexicon_rates("")
    assert set(rates) == set(LEXICONS)
    assert all(value == 0.0 for value in rates.values())


def test_passage_rows_carry_deal_and_family() -> None:
    passages = [
        {
            "passage_id": "p1",
            "deal_id": "d1",
            "document_family": "merger_agreement",
            "text": MERGER_CLAUSE,
        },
        {
            "passage_id": "p2",
            "deal_id": "d1",
            "document_family": "press_release_exhibit",
            "text": PRESS_LINE,
        },
        {
            "passage_id": "p3",
            "deal_id": "d2",
            "document_family": "press_release_exhibit",
            "text": PRESS_LINE,
        },
    ]
    rows = passage_tone_rows(passages)
    assert [row["passage_id"] for row in rows] == ["p1", "p2", "p3"]
    assert rows[0]["raw_or_adjusted"] == "raw"
    assert rows[0]["rate_retention_per100"] > 0


def test_deal_summary_uses_unweighted_passage_means() -> None:
    passages = [
        {"passage_id": "p1", "deal_id": "d1", "text": "retention bonus retention bonus"},
        {"passage_id": "p2", "deal_id": "d1", "text": "nothing relevant here at all"},
    ]
    summary = deal_tone_summary(passage_tone_rows(passages))
    assert len(summary) == 1
    row = summary[0]
    assert row["passage_count"] == 2
    raw_rate = float(row["rate_retention_per100"])
    single = lexicon_rates("retention bonus retention bonus")["retention"]
    zero = lexicon_rates("nothing relevant here at all")["retention"]
    assert abs(raw_rate - (single + zero) / 2) < 0.01


def test_family_baseline_with_fallback_recorded() -> None:
    passages = [
        {
            "passage_id": f"m{i}",
            "deal_id": f"d{i}",
            "document_family": "merger_agreement",
            "text": "employees shall receive retention and vesting on termination",
        }
        for i in range(5)
    ] + [
        {
            "passage_id": f"p{i}",
            "deal_id": f"d{i}",
            "document_family": "press_release_exhibit",
            "text": "welcome the team",
        }
        for i in range(2)
    ]
    rows = passage_tone_rows(passages)
    baselines, global_means = compute_family_baselines(
        rows, config=BaselineConfig(min_group_size=5)
    )
    merger = [
        b for b in baselines if b.document_family == "merger_agreement" and b.metric == "retention"
    ]
    press = [
        b
        for b in baselines
        if b.document_family == "press_release_exhibit" and b.metric == "retention"
    ]
    assert merger and not merger[0].fallback_to_global
    assert press[0].fallback_to_global
    assert abs(press[0].mean_rate - round(global_means["retention"], 4)) < 1e-6

    adjusted = apply_baselines(rows, baselines, config=BaselineConfig(min_group_size=5))
    sample = adjusted[0]
    assert sample["raw_or_adjusted"] == "raw_and_baseline_adjusted"
    expected = float(sample["rate_retention_per100"]) - float(sample["baseline_mean_retention"])
    assert abs(float(sample["rate_retention_per100_adjusted"]) - expected) < 0.01
