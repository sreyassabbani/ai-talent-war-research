"""Offline tests for deterministic AI-relevance screening."""

from __future__ import annotations

from tag_edgar.ai_screening import (
    classify_ai_category,
    classify_talent_motive,
    detect_talent_signals,
    normalize_transaction_form,
    screen_ai_text,
    screen_ai_text_for_target,
    target_anchors,
)

PRESS_RELEASE = (
    "Anytown, Calif. — July 15, 2021 — Acme Corp today announced it has acquired "
    "WidgetMind, a machine learning startup whose platform helps enterprises build "
    "artificial intelligence applications. WidgetMind's founding team will join Acme's "
    "cloud division."
)

NON_AI = "Acme Corp announced the acquisition of Generic Plumbing Supply Co. The deal closed."

ROBOTICS_ONLY = "Acme acquired RobotCo, a robotics integrator for warehouse automation."


def test_press_release_qualifies_with_excerpts() -> None:
    result = screen_ai_text(PRESS_RELEASE)
    assert result.qualifies
    assert "machine learning" in result.distinct_terms
    assert "artificial intelligence" in result.distinct_terms
    assert all(hit.excerpt for hit in result.hits)
    assert any("machine learning" in hit.excerpt for hit in result.hits)


def test_target_link_prevents_generic_corporate_ai_false_positive() -> None:
    generic = (
        "Microsoft acquired Lobe in September. "
        + ("unrelated disclosure " * 100)
        + "Microsoft invests in artificial intelligence and machine learning products."
    )
    result = screen_ai_text_for_target(generic, "Lobe Artificial Intelligence")
    assert not result.qualifies

    linked = "Microsoft acquired Lobe, a machine learning design platform for AI models."
    linked_result = screen_ai_text_for_target(linked, "Lobe Artificial Intelligence")
    assert linked_result.qualifies
    assert "Lobe" in linked_result.best_excerpt


def test_ai_ml_abbreviation_qualifies_when_linked_to_target() -> None:
    text = "We acquired June.ai, a productivity tool that combines AI/ML and extraction."
    result = screen_ai_text_for_target(text, "June.ai")
    assert result.qualifies
    assert "ai/ml" in {hit.matched_text for hit in result.hits}


def test_explicit_computer_vision_or_ai_powering_is_sufficient() -> None:
    assert screen_ai_text_for_target(
        "6D.ai solves difficult computer vision software problems.", "6D.ai"
    ).qualifies
    assert screen_ai_text_for_target(
        "Caper is an AI-powered smart-cart platform.", "Caper AI"
    ).qualifies


def test_explicit_ai_capability_or_applied_ai_is_sufficient() -> None:
    assert screen_ai_text_for_target(
        "Replier.ai adds AI capability for marketing copy.", "Replier.ai"
    ).qualifies
    assert screen_ai_text_for_target(
        "Vertikal AI uses applied AI for predictive maintenance.", "Vertikal AI"
    ).qualifies


def test_target_anchors_remove_generic_ai_and_corporate_suffixes() -> None:
    assert target_anchors("Lobe Artificial Intelligence Inc") == ("lobe",)


def test_target_anchors_keep_short_digit_brand() -> None:
    assert target_anchors("6D.ai") == ("6d",)


def test_target_anchors_remove_descriptive_suffixes() -> None:
    assert target_anchors("Mapper.ai Inc-Mapping,Localiza") == ("mapper",)


def test_target_link_does_not_cross_paragraphs() -> None:
    unrelated_adjacent_bullets = (
        "Announced machine learning capabilities from Microsoft Azure.\n\n"
        "Welcomed the addition of the Butter.ai employee team to Box."
    )
    assert not screen_ai_text_for_target(
        unrelated_adjacent_bullets, "Butter AI Corp"
    ).qualifies


def test_non_ai_document_never_qualifies() -> None:
    result = screen_ai_text(NON_AI)
    assert not result.qualifies
    assert result.distinct_terms == ()
    assert result.best_excerpt == ""


def test_single_weak_term_does_not_qualify() -> None:
    result = screen_ai_text(ROBOTICS_ONLY)
    assert not result.qualifies


def test_hit_offsets_point_at_source_text() -> None:
    text = "The company builds computer vision systems for retail."
    hits = [hit for hit in screen_ai_text(text).hits if hit.weight >= 3]
    assert len(hits) == 1
    hit = hits[0]
    assert text[hit.match_start : hit.match_end].lower() == "computer vision"


def test_talent_join_language_detected() -> None:
    signals = detect_talent_signals(PRESS_RELEASE)
    assert signals.join_language
    assert not signals.acquihire_explicit
    assert any("founding team" in excerpt for excerpt in signals.join_excerpts)


def test_acquihire_and_license_hire_explicit_forms() -> None:
    acquihire = detect_talent_signals("This was primarily an acquire-to-hire transaction.")
    assert acquihire.acquihire_explicit
    license_hire = detect_talent_signals(
        "The parties entered a license-and-hire arrangement covering the models."
    )
    assert license_hire.license_and_hire_explicit
    plain = detect_talent_signals("The merger closed on Tuesday.")
    assert not plain.join_language and not plain.acquihire_explicit


def test_sdc_form_normalization() -> None:
    assert normalize_transaction_form("Merger") == "statutory merger"
    assert normalize_transaction_form("Acq. of Assets") == "asset purchase"
    assert normalize_transaction_form(None) == "unknown"
    assert normalize_transaction_form("").startswith("unknown")
    unmapped = normalize_transaction_form("Weird Form")
    assert unmapped.startswith("unmapped_sdc_form:")


def test_category_classification_rules() -> None:
    qualified = screen_ai_text(PRESS_RELEASE)
    signals = detect_talent_signals(PRESS_RELEASE)
    category = classify_ai_category(
        screen_result=qualified, talent_signals=signals, sdc_form="Merger"
    )
    assert category == "ai_company_acquisition"
    motive = classify_talent_motive(signals)
    assert motive == "documented_team_join_language"

    unknown = classify_ai_category(
        screen_result=screen_ai_text(ROBOTICS_ONLY),
        talent_signals=detect_talent_signals(ROBOTICS_ONLY),
        sdc_form="Merger",
    )
    assert unknown == "unknown"


def test_form_and_motive_stay_separate() -> None:
    """An acqui-hire motive flag must never change the legal transaction form."""
    signals = detect_talent_signals("This was an acquire-to-hire of the platform team.")
    category = classify_ai_category(
        screen_result=screen_ai_text("Their AI models are strong."),
        talent_signals=signals,
        sdc_form="Acq. of Assets",
    )
    assert category == "acqui_hire_or_team"
    assert normalize_transaction_form("Acq. of Assets") == "asset purchase"
