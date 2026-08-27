"""Deterministic AI-relevance screening of primary-source transaction documents.

This module never asserts that a deal "is AI" from a target name alone. It finds explicit
AI-related language in retrieved primary sources, records the exact matched term, weight,
character offsets, and a verbatim supporting excerpt, and classifies the AI category and
talent-motive signals with fixed rules. Every output remains reviewable against its source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Weighted, case-insensitive patterns for explicit AI relevance in deal documents.
# Strong terms are unambiguous AI technology references; moderate terms are
# AI-adjacent fields; weak terms alone can never qualify a document.
AI_EVIDENCE_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"artificial intelligence", 5),
    (
        r"\bai\b(?=[\s,-]*(?:platform|model|models|startup|company|software|technology|lab|labs|research|system|systems|capabilities|assistant|agent|agents|product|products))",
        5,
    ),
    (r"machine learning", 5),
    (r"deep learning", 5),
    (r"neural network", 5),
    (r"generative ai", 5),
    (r"large language model", 5),
    (r"\bllm(s)?\b", 5),
    (r"foundation model", 5),
    (r"natural language processing", 5),
    (r"computer vision", 3),
    (r"reinforcement learning", 4),
    (r"speech recognition", 3),
    (r"data science", 2),
    (r"cognitive computing", 4),
    (r"conversational ai", 5),
    (r"autonomous driving", 3),
    (r"self-driving", 3),
    (r"robotics", 2),
    (r"intelligent automation", 3),
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")
_PARAGRAPH_BREAK = re.compile(r"\n[\t \u00a0]*\n+")
_TARGET_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_GENERIC_TARGET_TOKENS = frozenset(
    {
        "ai",
        "artificial",
        "intelligence",
        "data",
        "science",
        "sciences",
        "company",
        "corp",
        "corporation",
        "inc",
        "incorporated",
        "llc",
        "limited",
        "ltd",
        "plc",
        "technology",
        "technologies",
        "robotic",
        "robotics",
        "mapping",
        "localization",
        "localiza",
        "lab",
        "labs",
        "software",
        "solutions",
        "systems",
    }
)

TALENT_JOIN_PATTERN = re.compile(
    r"\b(?:team|employees?|founders?|co-founders?|engineers?|researchers?|scientists?|"
    r"technical talent|workforce)\b[^.!?]{0,160}?\b(?:join|joins|joined|joining|"
    r"will join|become part of|move to|moving to)\b",
    re.IGNORECASE,
)
JOIN_TALENT_PATTERN = re.compile(
    r"\b(?:join|joins|joined|joining)\b[^.!?]{0,160}?\b"
    r"(?:team|employees?|founders?|co-founders?|engineers?|researchers?|scientists?|"
    r"technical talent|workforce)\b",
    re.IGNORECASE,
)
ACQUIHIRE_EXPLICIT_PATTERN = re.compile(
    r"acqui-hire|acquire[- ]to[- ]hire|talent acquisition|hiring rather than|"
    r"primarily for (?:its )?(?:team|talent|people)",
    re.IGNORECASE,
)
LICENSE_HIRE_PATTERN = re.compile(
    r"licen[sc]e .{0,80}(?:and|plus) .{0,40}(?:hiring|offer[s]?\s+(?:roles|positions)|team)|"
    r"(?:reverse acqui-hire|license-and-hire)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AiScreenResult:
    total_weight: int
    distinct_terms: tuple[str, ...]
    hits: tuple[AiEvidenceHit, ...]
    qualifies: bool

    @property
    def best_excerpt(self) -> str:
        return self.hits[0].excerpt if self.hits else ""


@dataclass(frozen=True)
class TalentSignals:
    join_language: bool
    join_excerpts: tuple[str, ...]
    acquihire_explicit: bool
    license_and_hire_explicit: bool


def split_sentences(text: str) -> list[tuple[int, int, str]]:
    """Return deterministic (start, end, sentence) triples over the source text."""
    sentences: list[tuple[int, int, str]] = []
    position = 0
    for raw in _SENTENCE_SPLIT.split(text):
        if not raw or not raw.strip():
            position += len(raw) + 1
            continue
        start = text.find(raw, position)
        if start < 0:
            start = position
        end = start + len(raw)
        sentences.append((start, end, raw))
        position = end
    return sentences


def _excerpt_for(sentence: str, max_chars: int = 400) -> str:
    collapsed = " ".join(sentence.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


@dataclass(frozen=True)
class AiEvidenceHit:
    label: str
    matched_text: str
    weight: int
    excerpt: str
    match_start: int
    match_end: int


def find_ai_hits(text: str) -> list[AiEvidenceHit]:
    """Find every AI-evidence hit; sorted by (-weight, position, label) for stability."""
    hits: list[AiEvidenceHit] = []
    for pattern, weight in AI_EVIDENCE_PATTERNS:
        compiled = re.compile(pattern, re.IGNORECASE)
        for sentence_start, _, sentence in split_sentences(text):
            for match in compiled.finditer(sentence):
                offset = sentence_start + match.start()
                hits.append(
                    AiEvidenceHit(
                        label=pattern,
                        matched_text=match.group(0).lower(),
                        weight=weight,
                        excerpt=_excerpt_for(sentence),
                        match_start=offset,
                        match_end=offset + len(match.group(0)),
                    )
                )
    return sorted(hits, key=lambda hit: (-hit.weight, hit.match_start, hit.label))


def screen_ai_text(text: str, *, qualifying_weight: int = 5) -> AiScreenResult:
    """Screen one document body for explicit AI evidence.

    A document qualifies only when the summed distinct-term weight reaches
    ``qualifying_weight`` using terms of weight >= 3, so a single weak mention such as
    "robotics" can never qualify on its own.
    """
    all_hits = find_ai_hits(text)
    substantive = [hit for hit in all_hits if hit.weight >= 3]
    by_label: dict[str, int] = {}
    for hit in substantive:
        by_label[hit.label] = max(by_label.get(hit.label, 0), hit.weight)
    total_weight = sum(by_label.values())
    distinct = tuple(sorted(by_label))
    return AiScreenResult(
        total_weight=total_weight,
        distinct_terms=distinct,
        hits=tuple(all_hits),
        qualifies=total_weight >= qualifying_weight,
    )


def target_anchors(target_name: str) -> tuple[str, ...]:
    """Return deterministic, non-generic tokens that can link evidence to a target."""
    tokens = [
        token.casefold()
        for token in _TARGET_TOKEN.findall(target_name)
        if (len(token) >= 3 or (len(token) >= 2 and any(char.isdigit() for char in token)))
        and token.casefold() not in _GENERIC_TARGET_TOKENS
    ]
    return tuple(dict.fromkeys(tokens))


def target_name_mentioned(text: str, target_name: str) -> bool:
    """Require a distinctive target-name anchor, not a generic ``AI`` suffix."""
    anchors = target_anchors(target_name)
    if not anchors:
        return False
    return any(
        re.search(rf"(?<!\w){re.escape(anchor)}(?!\w)", text, re.IGNORECASE) for anchor in anchors
    )


def screen_ai_text_for_target(
    text: str,
    target_name: str,
    *,
    qualifying_weight: int = 5,
    radius: int = 600,
) -> AiScreenResult:
    """Return only AI evidence locally linked to a distinctive target-name anchor.

    A large corporate filing can discuss AI generally while never discussing the candidate
    target. This screen prevents that generic disclosure from qualifying the transaction.
    Each retained hit must be within ``radius`` characters of a target anchor, and its
    supporting excerpt spans both the anchor and the AI term where practical.
    """
    anchors = target_anchors(target_name)
    if not anchors:
        return AiScreenResult(0, (), (), False)
    anchor_matches = [
        match
        for anchor in anchors
        for match in re.finditer(rf"(?<!\w){re.escape(anchor)}(?!\w)", text, re.IGNORECASE)
    ]
    paragraph_breaks = list(_PARAGRAPH_BREAK.finditer(text))

    def paragraph_bounds(position: int) -> tuple[int, int]:
        start = 0
        end = len(text)
        for boundary in paragraph_breaks:
            if boundary.end() <= position:
                start = boundary.end()
                continue
            if boundary.start() >= position:
                end = boundary.start()
                break
        return start, end

    linked: list[AiEvidenceHit] = []
    for hit in find_ai_hits(text):
        paragraph_start, paragraph_end = paragraph_bounds(hit.match_start)
        nearby = [
            match
            for match in anchor_matches
            if paragraph_start <= match.start() < paragraph_end
            if match.start() <= hit.match_end + radius and match.end() >= hit.match_start - radius
        ]
        if not nearby:
            continue
        closest = min(
            nearby,
            key=lambda match: min(
                abs(match.start() - hit.match_end), abs(hit.match_start - match.end())
            ),
        )
        excerpt_start = max(0, min(closest.start(), hit.match_start) - 160)
        excerpt_end = min(len(text), max(closest.end(), hit.match_end) + 240)
        linked.append(
            AiEvidenceHit(
                label=hit.label,
                matched_text=hit.matched_text,
                weight=hit.weight,
                excerpt=_excerpt_for(text[excerpt_start:excerpt_end], max_chars=800),
                match_start=hit.match_start,
                match_end=hit.match_end,
            )
        )
    substantive = [hit for hit in linked if hit.weight >= 3]
    by_label: dict[str, int] = {}
    for hit in substantive:
        by_label[hit.label] = max(by_label.get(hit.label, 0), hit.weight)
    total_weight = sum(by_label.values())
    return AiScreenResult(
        total_weight=total_weight,
        distinct_terms=tuple(sorted(by_label)),
        hits=tuple(sorted(linked, key=lambda hit: (-hit.weight, hit.match_start, hit.label))),
        qualifies=total_weight >= qualifying_weight,
    )


def detect_talent_signals(text: str) -> TalentSignals:
    join_excerpts: list[str] = []
    join_found = False
    for pattern in (TALENT_JOIN_PATTERN, JOIN_TALENT_PATTERN):
        for match in pattern.finditer(text):
            sentence_start = text.rfind(".", 0, match.start()) + 1
            sentence_end = text.find(".", match.end())
            sentence_end = len(text) if sentence_end < 0 else sentence_end + 1
            join_excerpts.append(_excerpt_for(text[sentence_start:sentence_end]))
            join_found = True
    return TalentSignals(
        join_language=join_found,
        join_excerpts=tuple(sorted(set(join_excerpts))),
        acquihire_explicit=bool(ACQUIHIRE_EXPLICIT_PATTERN.search(text)),
        license_and_hire_explicit=bool(LICENSE_HIRE_PATTERN.search(text)),
    )


_SDC_FORM_MAP: dict[str, str] = {
    "merger": "statutory merger",
    "acq. of assets": "asset purchase",
    "acq. cert. asts.": "asset purchase (certain assets)",
    "acq. maj. int.": "majority stock acquisition",
    "acq. rem. int.": "remaining-interest step acquisition",
    "acquisition": "stock/asset acquisition (unspecified)",
    "exchange offer": "exchange offer",
    "recapitalization": "recapitalization",
}


def normalize_transaction_form(raw_form: str | None) -> str:
    """Map an SDC ``Form`` value to a stable legal-form label.

    The legal transaction form stays separate from any business-motive flag.
    """
    if raw_form is None or not raw_form.strip():
        return "unknown"
    return _SDC_FORM_MAP.get(raw_form.strip().lower(), f"unmapped_sdc_form:{raw_form.strip()}")


def classify_ai_category(
    *,
    screen_result: AiScreenResult,
    talent_signals: TalentSignals,
    sdc_form: str | None,
) -> str:
    """Deterministic first-pass category; final labels remain subject to human review."""
    if not screen_result.qualifies and not (
        talent_signals.join_language or talent_signals.acquihire_explicit
    ):
        return "unknown"
    form = normalize_transaction_form(sdc_form)
    if talent_signals.license_and_hire_explicit:
        return "license_and_hire"
    if form == "asset purchase (certain assets)":
        return "ai_assets_or_ip"
    if talent_signals.acquihire_explicit:
        return "acqui_hire_or_team"
    if form in {"majority stock acquisition", "remaining-interest step acquisition"}:
        return "strategic_or_minority_investment"
    if form in {"statutory merger", "asset purchase"}:
        return "ai_company_acquisition"
    return "ai_related_transaction"


def classify_talent_motive(talent_signals: TalentSignals) -> str:
    """Business-motive flag derived only from explicit document language."""
    if talent_signals.acquihire_explicit:
        return "documented_acqui_hire_language"
    if talent_signals.join_language:
        return "documented_team_join_language"
    return "not_documented_in_reviewed_sources"
