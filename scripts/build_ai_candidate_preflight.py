"""Build a deterministic AI-transaction candidate preflight from an SDC export.

This is deliberately a candidate generator, not an AI-truth classifier. Every row
must be source-verified before it enters the qualifying 100-deal research sample.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


DATE_FORMATS = ("%m/%d/%y", "%m/%d/%Y")
TARGET_TERMS: tuple[tuple[str, int], ...] = (
    (r"\bai\b", 5),
    (r"artificial intelligence", 5),
    (r"deep\s*mind", 5),
    (r"machine learning", 5),
    (r"mosaicml", 5),
    (r"kaggle", 5),
    (r"semantic machines", 5),
    (r"lobe artificial", 5),
    (r"robotics?", 3),
    (r"autonom(?:ous|y)", 3),
    (r"computer vision", 3),
    (r"neural", 3),
    (r"natural language", 3),
    (r"speech (?:technology|recognition)", 3),
    (r"data science", 3),
    (r"cognitive", 3),
    (r"self[- ]driv", 3),
    (r"driverless", 3),
    (r"ctrl[- ]labs", 5),
)


@dataclass(frozen=True)
class Candidate:
    deal_id: str
    announcement_date: date
    target_name: str
    acquirer_name: str
    source_file: str
    source_row_number: int
    score: int
    matched_terms: str


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value: str) -> date | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    return None


def score_target(target_name: str) -> tuple[int, str]:
    score = 0
    terms: list[str] = []
    for pattern, points in TARGET_TERMS:
        if re.search(pattern, target_name, flags=re.IGNORECASE):
            score += points
            terms.append(pattern)
    return score, ";".join(terms)


def read_candidates(input_dir: Path, start_year: int, end_year: int) -> list[Candidate]:
    by_deal: dict[str, Candidate] = {}
    for path in sorted(input_dir.glob("ma_*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as file:
            next(file, None)
            reader = csv.DictReader(file)
            for row_number, raw_row in enumerate(reader, start=2):
                row = {
                    normalize_header(key or ""): (value or "").strip()
                    for key, value in raw_row.items()
                }
                deal_id = row.get("Deal Number", "")
                announced = parse_date(row.get("Date Announced", ""))
                target = row.get("Target Name", "")
                acquirer = row.get("Acquiror Ultimate Parent", "")
                if not deal_id or announced is None or not target:
                    continue
                if not start_year <= announced.year <= end_year:
                    continue
                score, matched_terms = score_target(target)
                if score == 0:
                    continue
                candidate = Candidate(
                    deal_id=deal_id,
                    announcement_date=announced,
                    target_name=target,
                    acquirer_name=acquirer,
                    source_file=path.name,
                    source_row_number=row_number,
                    score=score,
                    matched_terms=matched_terms,
                )
                prior = by_deal.get(deal_id)
                if prior is None or candidate.source_file < prior.source_file:
                    by_deal[deal_id] = candidate
    return sorted(by_deal.values(), key=lambda item: (-item.score, item.announcement_date, item.deal_id))


def selection_key(candidate: Candidate) -> str:
    return hashlib.sha256(f"ai-100-preflight:{candidate.deal_id}".encode()).hexdigest()


def write_output(candidates: list[Candidate], output: Path, limit: int) -> None:
    ranked = sorted(candidates, key=lambda item: (-item.score, selection_key(item), item.deal_id))
    selected = {candidate.deal_id for candidate in ranked[:limit]}
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "deal_id",
        "announcement_date",
        "target_name",
        "acquirer_name",
        "source_dataset",
        "source_file",
        "source_row_number",
        "candidate_score",
        "matched_target_terms",
        "selection_status",
        "ai_verification_status",
        "ai_relevance_evidence",
        "transaction_form",
        "talent_motive",
        "source_url",
    ]
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for candidate in ranked:
            writer.writerow(
                {
                    "deal_id": candidate.deal_id,
                    "announcement_date": candidate.announcement_date.isoformat(),
                    "target_name": candidate.target_name,
                    "acquirer_name": candidate.acquirer_name,
                    "source_dataset": "Thomson Reuters SDC export; discovery only",
                    "source_file": candidate.source_file,
                    "source_row_number": candidate.source_row_number,
                    "candidate_score": candidate.score,
                    "matched_target_terms": candidate.matched_terms,
                    "selection_status": (
                        "selected_candidate" if candidate.deal_id in selected else "reserve_candidate"
                    ),
                    "ai_verification_status": "pending_primary_source_review",
                    "ai_relevance_evidence": "not established by name screen",
                    "transaction_form": "unknown",
                    "talent_motive": "unknown",
                    "source_url": "",
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument("--end-year", type=int, default=2022)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    candidates = read_candidates(args.input_dir, args.start_year, args.end_year)
    write_output(candidates, args.output_csv, min(args.limit, len(candidates)))
    print(f"candidates={len(candidates)} selected={min(args.limit, len(candidates))}")


if __name__ == "__main__":
    main()
