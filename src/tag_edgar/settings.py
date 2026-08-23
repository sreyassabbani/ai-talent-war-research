from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    user_agent: str
    cache_dir: Path
    rate_per_second: float
    forms: frozenset[str]
    document_prefixes: tuple[str, ...]
    patterns: dict[str, tuple[str, ...]]
    expanded_forms: frozenset[str] = field(default_factory=frozenset)

    def selected_forms(self, include_expanded: bool = False) -> frozenset[str]:
        """Return the configured retrieval form set for a reproducible run."""
        return self.forms | self.expanded_forms if include_expanded else self.forms


def _read_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as file:
        return tomllib.load(file)


def load_settings(require_user_agent: bool = True) -> Settings:
    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if require_user_agent and not user_agent:
        raise RuntimeError(
            "SEC_USER_AGENT is required for live requests. Copy .env.example to .env and use a "
            "real contact address."
        )

    raw_rate = os.environ.get("TAG_EDGAR_RATE_PER_SECOND", "5")
    try:
        rate_per_second = float(raw_rate)
    except ValueError as error:
        raise RuntimeError("TAG_EDGAR_RATE_PER_SECOND must be a positive number.") from error
    if not 0 < rate_per_second <= 10:
        raise RuntimeError("TAG_EDGAR_RATE_PER_SECOND must be greater than 0 and at most 10.")

    forms_config = _read_toml(PROJECT_ROOT / "config" / "forms.toml")
    pattern_config = _read_toml(PROJECT_ROOT / "config" / "patterns.toml")
    core = forms_config["core"]
    expanded = forms_config["expanded"]
    documents = forms_config["documents"]
    if not isinstance(core, dict) or not isinstance(expanded, dict) or not isinstance(documents, dict):
        raise TypeError("Invalid forms configuration.")
    form_values = core["forms"]
    expanded_form_values = expanded["forms"]
    prefix_values = documents["prefixes"]
    if (
        not isinstance(form_values, list)
        or not isinstance(expanded_form_values, list)
        or not isinstance(prefix_values, list)
    ):
        raise TypeError("Invalid form list configuration.")

    patterns: dict[str, tuple[str, ...]] = {}
    for category, values in pattern_config.items():
        if not isinstance(values, dict) or not isinstance(values.get("patterns"), list):
            raise TypeError(f"Invalid pattern configuration for {category}.")
        patterns[category] = tuple(str(value).lower() for value in values["patterns"])

    return Settings(
        user_agent=user_agent,
        cache_dir=Path(os.environ.get("TAG_EDGAR_CACHE_DIR", PROJECT_ROOT / "cache" / "http")),
        rate_per_second=rate_per_second,
        forms=frozenset(str(value).upper() for value in form_values),
        expanded_forms=frozenset(str(value).upper() for value in expanded_form_values),
        document_prefixes=tuple(str(value).upper() for value in prefix_values),
        patterns=patterns,
    )
