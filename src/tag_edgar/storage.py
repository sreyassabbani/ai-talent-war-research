from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any


def write_csv(path: Path, rows: Iterable[Any], fieldnames: list[str]) -> None:
    materialized = [asdict(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(materialized)
