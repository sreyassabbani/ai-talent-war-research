#!/usr/bin/env bash
# Everything after retrieval: corpus, freeze, AI labels, topics, tone, report.
#
# Retrieval (tag-edgar run-disclosure-sample) is the only live step and must finish first.
# Every command below is offline and deterministic, so this script can be re-run safely.
#
# The freeze decides the sample. Every step after it runs on the frozen deal list, never on the
# full retrieval queue, so the deal count in the report is the deal count the model saw.
#
# Every output path is overridable, and the defaults are the cycle-5 paths this script has always
# written. A later cycle sets them to its own directories and runs this same script, so the two
# cycles differ in their inputs and never in their code path -- the same reason the second-level
# model is a corpus subset rather than a flag inside the fitter.
#
# Usage:  bash scripts/run_disclosure_analysis.sh
#         CORPUS=... TOPICS=... bash scripts/run_disclosure_analysis.sh   # another cycle
set -euo pipefail

PY="${PY:-.venv/Scripts/python.exe}"
D=data/derived
QUEUE="$D/disclosure_review_queue.csv"
RUNS="$D/disclosure_runs"
SEED=20260823

CORPUS="${CORPUS:-$D/employee_corpus_100}"
TOPICS="${TOPICS:-$D/employee_topics_100}"
FROZEN_SAMPLE="${FROZEN_SAMPLE:-$D/disclosure_frozen_sample}"
FROZEN_QUEUE="${FROZEN_QUEUE:-$D/disclosure_frozen_queue.csv}"
LABELS="${LABELS:-$D/deal_ai_labels}"
TONE="${TONE:-$D/employee_tone_100}"
REVIEW="${REVIEW:-$D/employee_topic_review_100}"
REPORT="${REPORT:-docs/disclosure_sample_report.md}"
AUDIT_STATE="${AUDIT_STATE:-not run for this cycle}"

echo "== 1/8 corpus =="
# --no-manual-coding: the manually coded positive sources belong to the ten pilot deals, which
# this sample does not contain. Leaving the gate on would fail it for the wrong reason.
$PY -m tag_edgar.cli build-employee-corpus "$QUEUE" "$RUNS" \
  --output-dir "$CORPUS" --no-manual-coding

echo "== 2/8 freeze the modelled sample =="
$PY -m tag_edgar.cli freeze-disclosure-sample "$QUEUE" "$CORPUS/passages.csv" "$RUNS" \
  --probe-csv "$D/disclosure_probe/probe_results.csv" \
  --output-dir "$FROZEN_SAMPLE"

echo "== 3/8 restrict the queue to the frozen sample =="
$PY scripts/restrict_queue_to_frozen.py "$QUEUE" \
  "$FROZEN_SAMPLE/frozen_sample.csv" "$FROZEN_QUEUE"

echo "== 4/8 AI and talent labels (after selection) =="
$PY -m tag_edgar.cli label-deal-ai "$FROZEN_QUEUE" "$CORPUS" --output-dir "$LABELS"

echo "== 5/8 topic model, prespecified primary settings =="
$PY -m tag_edgar.cli analyze-employee-topics "$FROZEN_QUEUE" "$CORPUS" \
  --output-dir "$TOPICS" --seed "$SEED" --k-min 3 --k-max 7 \
  --fit-balance source_family --max-fit-passages 1500

echo "== 6/8 sensitivity: the two other fit-balance modes =="
for mode in deal none; do
  $PY -m tag_edgar.cli analyze-employee-topics "$FROZEN_QUEUE" "$CORPUS" \
    --output-dir "${TOPICS}_${mode}" --seed "$SEED" --k-min 3 --k-max 7 \
    --fit-balance "$mode" --max-fit-passages 1500
done

echo "== 7/8 tone (secondary diagnostic) and the blinded topic-review packet =="
$PY -m tag_edgar.cli analyze-employee-tone "$CORPUS/passages.csv" \
  --output-dir "$TONE"
$PY -m tag_edgar.cli prepare-employee-topic-review \
  "$TOPICS/canonical_topic_assignments.csv" "$CORPUS/passages.csv" \
  --output-dir "$REVIEW"

echo "== 8/8 report =="
# The corpus relevance audit was not run for this cycle, by direction. The report states that
# in place of a passing gate; it never claims one.
# Every cycle-specific input is passed. Passing only --corpus-dir and --topics-dir left
# --frozen-dir, --ai-labels-dir and --tone-dir on their cycle-5 defaults, so the cycle-6 report
# was written with a cycle-6 corpus and model against a cycle-5 sample, labels and tone. Nothing
# failed; the headline deal and passage counts were simply the previous cycle's.
$PY scripts/build_disclosure_sample_report.py \
  --corpus-dir "$CORPUS" --topics-dir "$TOPICS" \
  --frozen-dir "$FROZEN_SAMPLE" \
  --ai-labels-dir "$LABELS" \
  --tone-dir "$TONE" \
  --audit-state "$AUDIT_STATE" \
  --output "$REPORT"

echo "Done. Report: $REPORT"
