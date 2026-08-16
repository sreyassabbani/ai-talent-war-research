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
    lower_text = text.lower()
    evidence: list[Evidence] = []
    for category, category_patterns in patterns.items():
        for pattern in category_patterns:
            match = re.search(re.escape(pattern), lower_text)
            if match is None:
                continue
            start = max(0, match.start() - 250)
            end = min(len(text), match.end() + 350)
            excerpt = " ".join(text[start:end].split())
            score = 1
            if document.is_primary:
                score += 2
            if document.document_type and document.document_type.startswith("EX-2."):
                score += 2
            if target_name and target_name.lower() in excerpt.lower():
                score += 1
            digest = hashlib.sha256(
                f"{deal_id}:{document.document_id}:{category}:{pattern}".encode()
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
                )
            )
    return evidence
