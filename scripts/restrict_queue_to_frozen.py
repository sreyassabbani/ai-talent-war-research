"""Restrict the retrieval queue to the deals the freeze accepted for modelling.

The retrieval queue is deliberately wider than the sample: it holds every deal worth trying,
including those that turn out to carry no employee language. The freeze decides which of them
have enough text to characterise. Running the model on the wider queue would report a different
deal count than the sample the report describes, so every step after the freeze reads this file.

Usage:
    python scripts/restrict_queue_to_frozen.py <queue.csv> <frozen_sample.csv> <out.csv>
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

MODELLED = "modelled"


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    queue_path, frozen_path, out_path = (Path(value) for value in argv[1:4])

    with frozen_path.open(newline="", encoding="utf-8") as file:
        keep = {
            row["deal_id"]
            for row in csv.DictReader(file)
            if row.get("sample_status") == MODELLED
        }
    if not keep:
        print(f"{frozen_path} lists no modelled deals.", file=sys.stderr)
        return 1

    with queue_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        print(f"{queue_path} is empty.", file=sys.stderr)
        return 1

    selected = [row for row in rows if row["deal_id"] in keep]
    missing = keep - {row["deal_id"] for row in selected}
    if missing:
        # A frozen deal absent from the queue would silently shrink the sample.
        print(
            f"{len(missing)} frozen deals are missing from the queue: {sorted(missing)[:5]}",
            file=sys.stderr,
        )
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(selected)
    print(f"frozen queue: {len(selected)} deals -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
