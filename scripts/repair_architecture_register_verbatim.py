"""Replace paraphrased register claims with verbatim SEC text, or withdraw the claim.

The generator requires a verbatim excerpt behind every asserted attribute. The register was
written from a human-curated salvage record whose excerpts are paraphrases, so each row has to
either gain the filing's own words or stop asserting anything.

This does exactly two things per row, and never anything in between:

* Extracts a quote from the cached filing with a pattern chosen for that specific claim, and
  verifies the result is an exact substring of that document before writing it.
* Where no passage in the document supports the claim, sets the value to unknown and keeps the
  explanatory paraphrase as a limitation.

Withdrawing a claim is the safe direction. Attaching a nearby-but-unsupporting quote would look
like evidence while proving nothing, which is worse than the paraphrase it replaced.

Usage:
    python scripts/repair_architecture_register_verbatim.py [--check]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tag_edgar.deal_retrieval import html_to_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTER = PROJECT_ROOT / "config" / "pilot_deal_architecture_evidence.csv"
CACHE = PROJECT_ROOT / "cache" / "http"

# (deal_id, attribute) -> regular expression selecting the supporting text in that deal's cited
# document. Every pattern was chosen by reading the document and confirming the match states the
# claim rather than merely mentioning its subject. Pairs absent from this table are withdrawn.
QUOTES: dict[tuple[str, str], str] = {
    # Legal form: the agreement's own title names the transaction structure.
    ("3783818020", "legal_transaction_form"): r"This EQUITY PURCHASE AGREEMENT[^.]{0,150}\.",
    ("3741094020", "legal_transaction_form"): r"TRANSACTION AGREEMENT dated as of [^.]{0,140}",
    ("3847595020", "legal_transaction_form"): r"AGREEMENT AND PLAN OF MERGER dated as of [^.]{0,120}",
    ("3705005020", "legal_transaction_form"): r"THIS AGREEMENT AND PLAN OF MERGER[^.]{0,150}\.",
    ("3968186020", "legal_transaction_form"): r"EQUITY PURCHASE AND MERGER AGREEMENT BY AND AMONG[^.]{0,150}",
    ("3859429020", "legal_transaction_form"): r"AGREEMENT AND PLAN OF MERGER among TAKE-TWO[^.]{0,130}",
    ("3948517040", "legal_transaction_form"): r"AGREEMENT AND PLAN OF MERGER by and among[^.]{0,130}",
    ("3700303020", "legal_transaction_form"): r"ASSET PURCHASE AGREEMENT between[^.]{0,140}",
    # Scope and control: the operative clause that moves the entity or the assets.
    ("3705005020", "scope_and_control"): (
        r"Upon the terms and subject to the conditions set forth in this Agreement, at the "
        r"Effective Time, Merger Sub shall be merged with and into the Company[^.]{0,200}\."
    ),
    ("3847595020", "scope_and_control"): (
        r"At the Effective Time, Merger Subsidiary shall be merged with and into the Company"
        r"[^.]{0,220}\."
    ),
    ("3859429020", "scope_and_control"): (
        r"at the Effective Time, Merger Sub 1 will merge with and into the Company[^.]{0,200}\."
    ),
    ("3948517040", "scope_and_control"): (
        r"[^.]{0,130}shall be merged with and into the Company \(as the absorbing company"
        r"[^.]{0,160}\."
    ),
    ("3700303020", "scope_and_control"): (
        r"[^.]{0,180}shall purchase, acquire, accept and pay for the Transferred Assets and "
        r"assume the Assumed Liabilities\."
    ),
    # Employee treatment: clauses that state what happens to people, not definitions about them.
    ("3783818020", "workforce_movement"): (
        r"Purchaser will, and will cause its Subsidiaries to, provide to such Continuing Employee "
        r"a base salary rate or base hourly wage rate[^.]{0,220}\."
    ),
    ("3948517040", "workforce_movement"): (
        r"each Continuing Employee shall be credited[^.]{0,240}\."
    ),
    ("3700303020", "workforce_movement"): (
        r"Buyer shall recognize, and permit such Transferred Employees to use[^.]{0,200}\."
    ),
    ("3968186020", "workforce_movement"): (
        r"accrued and unpaid severance relating to terminations occurring prior to the Closing"
        r"[^.]{0,240}"
    ),
    # Talent salience: a priced, employee-specific instrument in the agreement itself.
    ("3783818020", "talent_salience_signal"): (
        r"the Company, through its payroll system and less applicable Tax withholding, will pay "
        r"the Transaction Bonuses[^.]{0,180}\."
    ),
    ("3968186020", "talent_salience_signal"): (
        r"outstanding retention bonuses, calculated on a pro rata basis[^.]{0,200}"
    ),
    ("3700303020", "talent_salience_signal"): (
        r"Concurrently with the execution and delivery of this Agreement, the Key Employees have "
        r"entered into offer letter agreements with a Buyer Party[^.]{0,220}\."
    ),
    # Continuity: the announcement names the executive who stays and to whom he reports.
    ("2647141020", "business_product_continuity"): (
        r"Mark Benjamin will remain CEO of Nuance, reporting to[^.]{0,140}\."
    ),
}

WITHDRAWN_LIMITATION = (
    "Withdrawn under the verbatim-evidence rule: no passage in the cited document states this, "
    "so the attribute is recorded as unknown rather than asserted. Prior reading, retained for "
    "context only: "
)


def cached_text(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    body, meta = CACHE / f"{digest}.body", CACHE / f"{digest}.json"
    if not body.exists():
        return ""
    content_type = ""
    if meta.exists():
        try:
            content_type = str(json.loads(meta.read_text(encoding="utf-8")).get("content_type", ""))
        except (OSError, ValueError):
            pass
    return re.sub(r"\s+", " ", html_to_text(body.read_bytes(), content_type))


def repair(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    texts: dict[str, str] = {}
    notes: list[str] = []
    out: list[dict[str, str]] = []
    for row in rows:
        row = dict(row)
        asserted = row["machine_value"] != "unknown" and row["evidence_basis"] != "unknown"
        if not asserted or row["excerpt_kind"] == "verbatim":
            out.append(row)
            continue

        key = (row["deal_id"], row["attribute"])
        pattern = QUOTES.get(key)
        url = row["source_url"]
        if url not in texts:
            texts[url] = cached_text(url)
        text = texts[url]
        match = re.search(pattern, text) if (pattern and text) else None

        if match:
            quote = match.group(0).strip()
            if quote not in text:
                raise AssertionError(f"{key}: extracted quote is not a substring of the document.")
            row["evidence_excerpt"] = quote
            row["excerpt_kind"] = "verbatim"
            notes.append(f"verbatim  {key[0]} {key[1]}")
        else:
            previous = row["evidence_excerpt"].strip()
            row["machine_value"] = "unknown"
            row["evidence_basis"] = "unknown"
            row["evidence_status"] = "unknown"
            row["limitation"] = (WITHDRAWN_LIMITATION + previous)[:600]
            notes.append(f"withdrawn {key[0]} {key[1]}")
        out.append(row)
    return out, notes


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip())
    parser.add_argument(
        "--check", action="store_true", help="Report what would change without writing."
    )
    args = parser.parse_args(argv[1:])

    with REGISTER.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        fields = list(reader.fieldnames or [])
        rows = [{k: (v or "") for k, v in r.items()} for r in reader]

    repaired, notes = repair(rows)
    verbatim = sum(1 for note in notes if note.startswith("verbatim"))
    withdrawn = sum(1 for note in notes if note.startswith("withdrawn"))
    for note in notes:
        print("  " + note)
    print(f"\nverbatim: {verbatim}   withdrawn: {withdrawn}   unchanged: {len(rows) - len(notes)}")

    if args.check:
        return 0
    with REGISTER.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(repaired)
    print(f"Wrote {REGISTER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
