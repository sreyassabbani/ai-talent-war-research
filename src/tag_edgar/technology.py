from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TechnologyScreen:
    version: str
    source: str
    codes: dict[str, str]

    def rationale(self, sic: str) -> str | None:
        label = self.codes.get(sic.strip())
        if label is None:
            return None
        return f"Target SIC {sic.strip()}: {label}"


def load_technology_screen(path: Path) -> TechnologyScreen:
    with path.open("rb") as file:
        config = tomllib.load(file)
    version = config.get("version")
    source = config.get("source")
    codes = config.get("codes")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Technology-screen TOML needs a non-empty version.")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Technology-screen TOML needs a non-empty source URL or citation.")
    if not isinstance(codes, dict) or not codes:
        raise ValueError("Technology-screen TOML needs a non-empty [codes] table.")
    normalized = {str(code).strip(): str(label).strip() for code, label in codes.items()}
    if any(not code.isdigit() or not label for code, label in normalized.items()):
        raise ValueError("Technology-screen codes must be numeric and labels must be non-empty.")
    return TechnologyScreen(version.strip(), source.strip(), normalized)
