"""Exact paragraph-level source links built on the URL text-fragment directive.

A canonical ``source_url`` identifies the document a passage came from. It does not tell a reader
*where* in a long merger agreement the passage sits. The `text fragment
<https://wicg.github.io/scroll-to-text-fragment/>`_ directive (``#:~:text=``) lets a supporting
browser scroll to and highlight the exact quoted text.

The helper never invents a source. It returns an explicit unsupported status instead of a guessed
URL whenever the input URL is missing or not an absolute web URL, the quote carries no usable
text, or the document format cannot honour a text fragment. Callers keep both values: the
canonical ``source_url`` always resolves, and ``source_highlight_url`` is a best-effort deep link.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote as percent_encode
from urllib.parse import urlsplit, urlunsplit

__all__ = [
    "MAX_FRAGMENT_CHARS",
    "MIN_FRAGMENT_CHARS",
    "HighlightLink",
    "highlight_link",
    "text_fragment_url",
]

# Browsers cap how much text they will match, and very long directives are brittle: any single
# character of whitespace or entity normalisation drift breaks the match. Bound the fragment and
# fall back to a start/end pair for long passages.
MAX_FRAGMENT_CHARS = 300
#: Below this many characters a fragment matches too much unrelated text to be a useful anchor.
MIN_FRAGMENT_CHARS = 12

_WHITESPACE = re.compile(r"\s+")
# Soft hyphens and zero-width characters survive HTML extraction but are not present in the
# rendered text the browser matches against.
_INVISIBLE = re.compile("[\u00ad\u200b-\u200f\ufeff]")

_SUPPORTED_SCHEMES = frozenset({"http", "https"})
# Text fragments are honoured for HTML and plain text. PDF and XML documents render through
# viewers that ignore the directive, so a highlight URL would be a false promise.
_UNSUPPORTED_SUFFIXES = (".pdf", ".xml", ".xsd", ".xbrl", ".zip", ".jpg", ".png", ".gif")

_STATUS_OK = "ok"
_STATUS_NO_URL = "unsupported_missing_url"
_STATUS_BAD_URL = "unsupported_non_absolute_url"
_STATUS_FORMAT = "unsupported_document_format"
_STATUS_NO_TEXT = "unsupported_empty_quote"
_STATUS_SHORT = "unsupported_quote_too_short"


@dataclass(frozen=True)
class HighlightLink:
    """The outcome of building one highlight URL.

    ``url`` is empty whenever ``status`` is not ``ok``; it is never a fabricated or partial link.
    """

    url: str
    status: str
    fragment_kind: str = ""

    @property
    def supported(self) -> bool:
        return self.status == _STATUS_OK


def _normalize_quote(text: str) -> str:
    """Collapse extracted-text artefacts so the directive matches the rendered document."""
    cleaned = _INVISIBLE.sub("", text.replace("\u00a0", " "))
    return _WHITESPACE.sub(" ", cleaned).strip()


def _encode_directive_text(text: str) -> str:
    """Percent-encode one text-directive component.

    ``-``, ``,`` and ``&`` delimit the directive grammar, so they must be encoded even though they
    are otherwise legal in a fragment. Everything outside the unreserved set is encoded too, which
    keeps non-ASCII quotes valid as UTF-8 percent-escapes.

    ``quote`` treats ``-`` as always-safe, so it is escaped separately. That rewrite cannot corrupt
    the percent-escapes ``quote`` produced, because those contain only ``%`` and hex digits.
    """
    return percent_encode(text, safe="").replace("-", "%2D")


def _bounded_components(quote: str) -> tuple[tuple[str, ...], str]:
    """Return the directive components and which fragment shape they represent."""
    if len(quote) <= MAX_FRAGMENT_CHARS:
        return (quote,), "exact"

    # A textStart,textEnd pair anchors the same passage without embedding the whole paragraph.
    half = MAX_FRAGMENT_CHARS // 2
    start = _trim_to_word_boundary(quote[:half], from_end=True)
    end = _trim_to_word_boundary(quote[-half:], from_end=False)
    if not start or not end:
        return (quote[:MAX_FRAGMENT_CHARS].strip(),), "truncated"
    return (start, end), "range"


def _trim_to_word_boundary(chunk: str, *, from_end: bool) -> str:
    """Trim a slice back to a whole word so the directive does not start mid-token."""
    if from_end:
        head, _, tail = chunk.rpartition(" ")
        trimmed = head if head and tail else chunk
    else:
        _, _, tail = chunk.partition(" ")
        trimmed = tail if tail else chunk
    return trimmed.strip()


def _document_format_supported(path: str) -> bool:
    lowered = path.lower()
    return not lowered.endswith(_UNSUPPORTED_SUFFIXES)


def highlight_link(url: str | None, quote: str | None) -> HighlightLink:
    """Build a text-fragment deep link for ``quote`` within ``url``.

    Any existing query string is preserved untouched, and an existing fragment identifier is kept
    ahead of the appended ``:~:`` directive so both continue to work.
    """
    if not url or not url.strip():
        return HighlightLink("", _STATUS_NO_URL)

    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in _SUPPORTED_SCHEMES or not parts.netloc:
        return HighlightLink("", _STATUS_BAD_URL)
    if not _document_format_supported(parts.path):
        return HighlightLink("", _STATUS_FORMAT)

    if quote is None:
        return HighlightLink("", _STATUS_NO_TEXT)
    normalized = _normalize_quote(quote)
    if not normalized:
        return HighlightLink("", _STATUS_NO_TEXT)
    if len(normalized) < MIN_FRAGMENT_CHARS:
        return HighlightLink("", _STATUS_SHORT)

    components, kind = _bounded_components(normalized)
    directive = "text=" + ",".join(_encode_directive_text(part) for part in components)

    # Strip any directive this URL already carries; keep a plain fragment identifier as the anchor.
    existing_fragment = parts.fragment.split(":~:", 1)[0]
    fragment = f"{existing_fragment}:~:{directive}" if existing_fragment else f":~:{directive}"
    return HighlightLink(
        urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, fragment)),
        _STATUS_OK,
        kind,
    )


def text_fragment_url(url: str | None, quote: str | None) -> str:
    """Return a highlight URL, or an empty string when one cannot be built honestly."""
    return highlight_link(url, quote).url
