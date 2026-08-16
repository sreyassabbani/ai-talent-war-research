from __future__ import annotations

import hashlib
import re

from bs4 import BeautifulSoup

from .models import Document, Evidence
from .sec_client import SecClient


def document_text(client: SecClient, document: Document) -> str:
    content = client.get(document.url).content.decode("utf-8", errors="replace")
    if "<" in content[:500]:
        return BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
    return content


def find_evidence(
    deal_id: str,
    document: Document,
    text: str,
    patterns: dict[str, tuple[str, ...]],
    target_name: str | None = None,
) -> list[Evidence]:
    evidence: list[Evidence] = []
    for category, category_patterns in patterns.items():
        matches: list[tuple[int, int, str]] = []
        for pattern in category_patterns:
            expression = re.compile(
                rf"(?<![a-z0-9]){re.escape(pattern)}(?![a-z0-9])", re.IGNORECASE
            )
            matches.extend((match.start(), match.end(), pattern) for match in expression.finditer(text))

        # Prefer the most specific configured phrase when two patterns begin at the same offset,
        # such as "retention" and "retention bonus".
        distinct_matches: list[tuple[int, int, str]] = []
        for match_start, match_end, pattern in sorted(
            matches, key=lambda item: (item[0], -(item[1] - item[0]), item[2])
        ):
            if distinct_matches and distinct_matches[-1][0] == match_start:
                continue
            distinct_matches.append((match_start, match_end, pattern))

        for match_start, match_end, pattern in distinct_matches:
            start = max(0, match_start - 250)
            end = min(len(text), match_end + 350)
            excerpt = " ".join(text[start:end].split())
            score = 1
            if document.is_primary:
                score += 2
            if document.document_type and document.document_type.startswith("EX-2."):
                score += 2
            if target_name and target_name.lower() in excerpt.lower():
                score += 1
            digest = hashlib.sha256(
                f"{deal_id}:{document.document_id}:{category}:{pattern}:{match_start}".encode()
            ).hexdigest()[:16]
            evidence.append(
                Evidence(
                    evidence_id=f"ev_{digest}",
                    deal_id=deal_id,
                    document_id=document.document_id,
                    category=category,
                    pattern=pattern,
                    excerpt=excerpt,
                    score=score,
                    match_start=match_start,
                    match_end=match_end,
                )
            )
    return evidence
