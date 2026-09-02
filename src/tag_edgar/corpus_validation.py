"""Resolve and propagate the human corpus-relevance validation state.

The passage screen is only validated once a human assessor has labelled the blinded relevance
audit packet and the scorer has applied the prespecified gates. Until then, every artifact built
on that corpus - topic models, tone tables, reports, and release manifests - must carry the
pending state forward instead of presenting the corpus as accepted.

This module reads only the manifests the audit workflow already writes. It never infers or fills
labels, and it treats the absence of any audit evidence as an unvalidated corpus.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

__all__ = [
    "STATUS_ABSENT",
    "STATUS_FAILED",
    "STATUS_PASSED",
    "STATUS_PENDING",
    "CorpusValidationState",
    "corpus_validation_diagnostic",
    "resolve_corpus_validation",
]

STATUS_PASSED = "passed_human_corpus_validation"
STATUS_FAILED = "failed_human_corpus_validation"
STATUS_PENDING = "pending_human_corpus_validation"
STATUS_ABSENT = "no_corpus_validation_evidence"

_DIAGNOSTIC_STAGE = "corpus_validation"
_DIAGNOSTIC_NAME = "human_relevance_audit_gate"


@dataclass(frozen=True)
class CorpusValidationState:
    """What the audit manifests establish about the corpus the downstream artifact used."""

    status: str
    gate_status: str
    candidate_csv_sha256: str
    detail: str
    evidence_path: str

    @property
    def accepted(self) -> bool:
        return self.status == STATUS_PASSED

    @property
    def blocks_release(self) -> bool:
        return not self.accepted

    def as_manifest(self) -> dict[str, object]:
        return {**asdict(self), "accepted": self.accepted}


def _load_json(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} must contain a JSON object.")
    return loaded


def _sha_matches(expected: str | None, manifest: dict[str, object]) -> bool:
    if expected is None:
        return True
    return str(manifest.get("candidate_csv_sha256", "")) == expected


def resolve_corpus_validation(
    audit_dir: Path | None,
    scores_dir: Path | None = None,
    *,
    expected_candidate_sha256: str | None = None,
) -> CorpusValidationState:
    """Derive the validation state from the prepared packet and, if present, its scores.

    ``expected_candidate_sha256`` is the hash of the ``passages.csv`` the downstream artifact was
    built from. When it is supplied, an audit prepared from a different corpus is reported as
    pending for *this* corpus rather than silently borrowing another corpus's verdict.
    """
    score_manifest = scores_dir / "score_manifest.json" if scores_dir else None
    if score_manifest is not None and score_manifest.exists():
        manifest = _load_json(score_manifest)
        sha = str(manifest.get("candidate_csv_sha256", ""))
        if not _sha_matches(expected_candidate_sha256, manifest):
            return CorpusValidationState(
                STATUS_PENDING,
                "pending",
                expected_candidate_sha256 or "",
                "Scored audit was prepared from a different passages.csv; this corpus has no "
                "completed human relevance audit of its own.",
                str(score_manifest),
            )
        gate = str(manifest.get("gate_status", "")).lower()
        if manifest.get("audit_status") == "scored_human_labels" and gate == "pass":
            return CorpusValidationState(
                STATUS_PASSED, gate, sha, "Human relevance audit passed.", str(score_manifest)
            )
        if manifest.get("audit_status") == "scored_human_labels" and gate == "fail":
            return CorpusValidationState(
                STATUS_FAILED,
                gate,
                sha,
                "Human relevance audit failed a prespecified gate.",
                str(score_manifest),
            )
        return CorpusValidationState(
            STATUS_PENDING,
            gate or "pending",
            sha,
            "Score manifest does not record a completed human-labelled pass or fail.",
            str(score_manifest),
        )

    audit_manifest = audit_dir / "audit_manifest.json" if audit_dir else None
    if audit_manifest is not None and audit_manifest.exists():
        manifest = _load_json(audit_manifest)
        sha = str(manifest.get("candidate_csv_sha256", ""))
        if not _sha_matches(expected_candidate_sha256, manifest):
            detail = "Prepared audit packet targets a different passages.csv than this corpus."
        elif manifest.get("labels_are_human_attested"):
            detail = "Packet reports attested labels but has not been scored."
        else:
            detail = "Blinded audit packet is prepared but has no human labels yet."
        return CorpusValidationState(
            STATUS_PENDING,
            str(manifest.get("gate_status", "pending")) or "pending",
            sha if _sha_matches(expected_candidate_sha256, manifest) else "",
            detail,
            str(audit_manifest),
        )

    return CorpusValidationState(
        STATUS_ABSENT,
        "pending",
        expected_candidate_sha256 or "",
        "No relevance audit packet or scores were supplied for this corpus.",
        "",
    )


def corpus_validation_diagnostic(state: CorpusValidationState) -> dict[str, str]:
    """Express the state as a diagnostic row so it joins the automated report gate.

    A pending corpus is reported as ``warning``: it is not a pass, so the gate cannot succeed,
    but it is also not a measured failure. Only a scored human audit can yield ``fail``.
    """
    if state.accepted:
        status = "pass"
    elif state.status == STATUS_FAILED:
        status = "fail"
    else:
        status = "warning"
    return {
        "stage": _DIAGNOSTIC_STAGE,
        "name": _DIAGNOSTIC_NAME,
        "value": state.status,
        "status": status,
        "detail": state.detail,
    }
