from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache

from bs4 import BeautifulSoup
from bs4.element import Tag

_BLOCK_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "li", "td", "pre"})
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_WORD = re.compile(r"\b[\w'’-]+\b", re.UNICODE)
_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_NUMBER = re.compile(r"(?<!\w)[+-]?(?:\d[\d,.]*)(?:%|\b)")

# This is an inclusion screen, not a theme taxonomy. It deliberately covers employment,
# compensation, equity, benefits, workforce relations, and leadership-continuity language so an
# unsupervised method can discover the themes inside the resulting corpus.
DEFAULT_EMPLOYEE_SCREEN_TERMS = (
    "employee",
    "employees",
    "employment",
    "personnel",
    "workforce",
    "worker",
    "workers",
    "labor",
    "labour",
    "collective bargaining",
    "union",
    "executive officer",
    "management team",
    "founder",
    "key person",
    "key employee",
    "continued employment",
    "continued service",
    "remain employed",
    "retention",
    "retain",
    "stay bonus",
    "transaction bonus",
    "compensation",
    "salary",
    "wages",
    "payroll",
    "bonus",
    "incentive award",
    "severance",
    "change in control",
    "equity award",
    "stock option",
    "restricted stock",
    "restricted stock unit",
    "rsu",
    "vesting",
    "benefit plan",
    "employee benefit",
    "pension",
)


@dataclass(frozen=True)
class CorpusDocument:
    deal_id: str
    document_id: str
    accession_number: str
    document_type: str
    source_url: str
    content: bytes | str
    content_type: str = ""


@dataclass(frozen=True)
class TextBlock:
    block_index: int
    heading: str | None
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class ParsedDocument:
    source_sha256: str
    text_sha256: str
    text: str
    blocks: tuple[TextBlock, ...]


@dataclass(frozen=True)
class EmployeePassage:
    passage_id: str
    deal_id: str
    document_id: str
    accession_number: str
    document_type: str
    source_url: str
    heading: str | None
    block_start: int
    block_end: int
    char_start: int
    char_end: int
    text: str
    model_text: str
    token_count: int
    screen_terms: tuple[str, ...]
    content_sha256: str
    duplicate_group_id: str
    occurrence_count: int


@dataclass(frozen=True)
class PassageOccurrence:
    occurrence_id: str
    passage_id: str
    deal_id: str
    document_id: str
    accession_number: str
    document_type: str
    source_url: str
    heading: str | None
    block_start: int
    block_end: int
    char_start: int
    char_end: int


@dataclass(frozen=True)
class EmployeeCorpus:
    passages: tuple[EmployeePassage, ...]
    occurrences: tuple[PassageOccurrence, ...]
    documents_scanned: int
    blocks_scanned: int
    blocks_matched: int


@dataclass(frozen=True)
class _PassageCandidate:
    document: CorpusDocument
    heading: str | None
    block_start: int
    block_end: int
    char_start: int
    char_end: int
    text: str
    model_text: str
    token_count: int
    screen_terms: tuple[str, ...]
    content_sha256: str


def _display_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def normalize_model_text(value: str) -> str:
    """Return stable, low-noise text suitable for lexical feature extraction."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = _URL.sub(" urltoken ", normalized)
    normalized = _NUMBER.sub(" numbertoken ", normalized)
    normalized = re.sub(r"[^\w'’-]+", " ", normalized, flags=re.UNICODE)
    normalized = normalized.replace("’", "'").replace("–", "-")
    return " ".join(normalized.split())


def _is_html(text: str, content_type: str) -> bool:
    if "html" in content_type.casefold():
        return True
    prefix = text[:1000].casefold()
    return any(marker in prefix for marker in ("<html", "<body", "<div", "<p", "<table"))


def _is_heading(tag: Tag, text: str) -> bool:
    if tag.name in _HEADING_TAGS:
        return True
    if len(_WORD.findall(text)) > 20:
        return False
    bold = tag.find(["b", "strong"])
    if isinstance(bold, Tag) and _display_text(bold.get_text(" ", strip=True)) == text:
        return True
    letters = [character for character in text if character.isalpha()]
    return bool(letters) and sum(character.isupper() for character in letters) / len(letters) >= 0.8


def _leaf_blocks(soup: BeautifulSoup) -> list[tuple[Tag, str]]:
    elements = [element for element in soup.find_all(_BLOCK_TAGS) if isinstance(element, Tag)]
    element_ids = {id(element) for element in elements}
    parents_with_blocks: set[int] = set()
    for element in elements:
        for parent in element.parents:
            if isinstance(parent, Tag) and id(parent) in element_ids:
                parents_with_blocks.add(id(parent))

    output: list[tuple[Tag, str]] = []
    for element in elements:
        if id(element) in parents_with_blocks:
            continue
        text = _display_text(element.get_text(" ", strip=True))
        if text:
            output.append((element, text))
    return output


def _split_long_block(text: str, max_block_words: int) -> list[tuple[str, int, int]]:
    words = list(_WORD.finditer(text))
    if len(words) <= max_block_words:
        return [(text, 0, len(text))]
    chunks: list[tuple[str, int, int]] = []
    for offset in range(0, len(words), max_block_words):
        chunk_words = words[offset : offset + max_block_words]
        start = chunk_words[0].start()
        end = chunk_words[-1].end()
        chunks.append((text[start:end], start, end))
    return chunks


def _structured_segments(text: str, content_type: str) -> list[tuple[str | None, str]]:
    if not _is_html(text, content_type):
        paragraphs = [_display_text(value) for value in re.split(r"\n\s*\n+", text)]
        return [(None, value) for value in paragraphs if value]

    soup = BeautifulSoup(text, "html.parser")
    for unwanted in soup.find_all(["script", "style", "noscript"]):
        unwanted.decompose()
    elements = _leaf_blocks(soup)
    if not elements:
        fallback = [_display_text(value) for value in soup.get_text("\n").splitlines()]
        return [(None, value) for value in fallback if value]

    heading: str | None = None
    segments: list[tuple[str | None, str]] = []
    for element, value in elements:
        if _is_heading(element, value):
            heading = value
            continue
        segments.append((heading, value))
    return segments


def parse_document(
    content: bytes | str, content_type: str = "", *, max_block_words: int = 220
) -> ParsedDocument:
    """Extract heading-aware text blocks from cached SEC bytes or decoded document text."""
    if max_block_words < 20:
        raise ValueError("max_block_words must be at least 20.")
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    decoded = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    segments = _structured_segments(decoded, content_type)
    extracted_parts: list[str] = []
    blocks: list[TextBlock] = []
    cursor = 0
    for heading, segment in segments:
        if extracted_parts:
            cursor += 1
        segment_start = cursor
        extracted_parts.append(segment)
        cursor += len(segment)
        for chunk, local_start, local_end in _split_long_block(segment, max_block_words):
            blocks.append(
                TextBlock(
                    block_index=len(blocks),
                    heading=heading,
                    text=chunk,
                    char_start=segment_start + local_start,
                    char_end=segment_start + local_end,
                )
            )
    extracted = "\n".join(extracted_parts)
    return ParsedDocument(
        source_sha256=hashlib.sha256(raw).hexdigest(),
        text_sha256=hashlib.sha256(_display_text(extracted).encode("utf-8")).hexdigest(),
        text=extracted,
        blocks=tuple(blocks),
    )


@cache
def _screen_pattern(term: str) -> re.Pattern[str]:
    tokens = [re.escape(token) for token in term.casefold().replace("–", "-").split()]
    if len(tokens) > 1 and not tokens[-1].endswith("s"):
        tokens[-1] = rf"{tokens[-1]}s?"
    expression = r"[\s-]+".join(tokens)
    return re.compile(rf"(?<![\w]){expression}(?![\w])", re.IGNORECASE)


def screen_employee_terms(
    text: str, terms: Sequence[str] = DEFAULT_EMPLOYEE_SCREEN_TERMS
) -> tuple[str, ...]:
    """Return the configured inclusion terms found as complete words or phrases."""
    normalized = unicodedata.normalize("NFKC", text).casefold().replace("–", "-")
    return tuple(term for term in terms if _screen_pattern(term).search(normalized))


def _context_range(blocks: Sequence[TextBlock], index: int, context_blocks: int) -> tuple[int, int]:
    heading = blocks[index].heading
    start = index
    end = index
    for candidate in range(index - 1, max(-1, index - context_blocks - 1), -1):
        if blocks[candidate].heading != heading:
            break
        start = candidate
    for candidate in range(index + 1, min(len(blocks), index + context_blocks + 1)):
        if blocks[candidate].heading != heading:
            break
        end = candidate
    return start, end


def _merged_ranges(
    blocks: Sequence[TextBlock], matched_indices: Sequence[int], context_blocks: int
) -> list[tuple[int, int]]:
    ranges = [_context_range(blocks, index, context_blocks) for index in matched_indices]
    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            prior_start, prior_end = merged[-1]
            if blocks[prior_start].heading == blocks[start].heading:
                merged[-1] = (prior_start, max(prior_end, end))
                continue
        merged.append((start, end))
    return merged


def _candidate_key(candidate: _PassageCandidate) -> tuple[str | int, ...]:
    document = candidate.document
    return (
        document.deal_id,
        document.document_id,
        document.accession_number,
        document.source_url,
        candidate.block_start,
        candidate.block_end,
    )


def _passage_candidates(
    document: CorpusDocument,
    parsed: ParsedDocument,
    terms: Sequence[str],
    context_blocks: int,
) -> tuple[list[_PassageCandidate], int]:
    matched_indices = [
        block.block_index
        for block in parsed.blocks
        if screen_employee_terms(block.text, terms)
    ]
    candidates: list[_PassageCandidate] = []
    for start, end in _merged_ranges(parsed.blocks, matched_indices, context_blocks):
        selected = parsed.blocks[start : end + 1]
        text = "\n".join(block.text for block in selected)
        heading = selected[0].heading
        analysis_text = "\n".join(filter(None, (heading, text)))
        display_text = _display_text(analysis_text)
        content_sha256 = hashlib.sha256(display_text.encode("utf-8")).hexdigest()
        candidates.append(
            _PassageCandidate(
                document=document,
                heading=heading,
                block_start=start,
                block_end=end,
                char_start=selected[0].char_start,
                char_end=selected[-1].char_end,
                text=text,
                model_text=normalize_model_text(analysis_text),
                token_count=len(_WORD.findall(text)),
                screen_terms=screen_employee_terms(analysis_text, terms),
                content_sha256=content_sha256,
            )
        )
    return candidates, len(matched_indices)


def build_employee_corpus(
    documents: Iterable[CorpusDocument],
    *,
    screen_terms: Sequence[str] = DEFAULT_EMPLOYEE_SCREEN_TERMS,
    context_blocks: int = 0,
    max_block_words: int = 220,
) -> EmployeeCorpus:
    """Build a deterministic, exact-deduplicated employee passage corpus.

    ``passages`` contains one canonical modeling row per normalized exact passage.
    ``occurrences`` retains every source location and points back to its canonical passage.
    """
    if context_blocks < 0:
        raise ValueError("context_blocks cannot be negative.")
    if not screen_terms:
        raise ValueError("screen_terms cannot be empty.")

    ordered_documents = sorted(
        documents,
        key=lambda item: (
            item.deal_id,
            item.document_id,
            item.accession_number,
            item.source_url,
        ),
    )
    candidates: list[_PassageCandidate] = []
    blocks_scanned = 0
    blocks_matched = 0
    for document in ordered_documents:
        parsed = parse_document(
            document.content, document.content_type, max_block_words=max_block_words
        )
        blocks_scanned += len(parsed.blocks)
        document_candidates, document_matches = _passage_candidates(
            document, parsed, screen_terms, context_blocks
        )
        candidates.extend(document_candidates)
        blocks_matched += document_matches

    by_content: defaultdict[str, list[_PassageCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_content[candidate.content_sha256].append(candidate)

    passages: list[EmployeePassage] = []
    occurrences: list[PassageOccurrence] = []
    for content_sha256 in sorted(by_content):
        group = sorted(by_content[content_sha256], key=_candidate_key)
        canonical = group[0]
        passage_id = f"passage_{content_sha256[:16]}"
        duplicate_group_id = f"duplicate_{content_sha256[:16]}"
        passages.append(
            EmployeePassage(
                passage_id=passage_id,
                deal_id=canonical.document.deal_id,
                document_id=canonical.document.document_id,
                accession_number=canonical.document.accession_number,
                document_type=canonical.document.document_type,
                source_url=canonical.document.source_url,
                heading=canonical.heading,
                block_start=canonical.block_start,
                block_end=canonical.block_end,
                char_start=canonical.char_start,
                char_end=canonical.char_end,
                text=canonical.text,
                model_text=canonical.model_text,
                token_count=canonical.token_count,
                screen_terms=canonical.screen_terms,
                content_sha256=content_sha256,
                duplicate_group_id=duplicate_group_id,
                occurrence_count=len(group),
            )
        )
        for candidate in group:
            occurrence_seed = ":".join(
                (
                    passage_id,
                    candidate.document.deal_id,
                    candidate.document.document_id,
                    str(candidate.block_start),
                    str(candidate.block_end),
                )
            )
            occurrence_id = f"occurrence_{hashlib.sha256(occurrence_seed.encode()).hexdigest()[:16]}"
            occurrences.append(
                PassageOccurrence(
                    occurrence_id=occurrence_id,
                    passage_id=passage_id,
                    deal_id=candidate.document.deal_id,
                    document_id=candidate.document.document_id,
                    accession_number=candidate.document.accession_number,
                    document_type=candidate.document.document_type,
                    source_url=candidate.document.source_url,
                    heading=candidate.heading,
                    block_start=candidate.block_start,
                    block_end=candidate.block_end,
                    char_start=candidate.char_start,
                    char_end=candidate.char_end,
                )
            )

    return EmployeeCorpus(
        passages=tuple(passages),
        occurrences=tuple(occurrences),
        documents_scanned=len(ordered_documents),
        blocks_scanned=blocks_scanned,
        blocks_matched=blocks_matched,
    )
