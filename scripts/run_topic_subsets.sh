#!/usr/bin/env bash
# Second-level topics: open up each first-level theme and model it again.
#
# Dr. Singh, 2026-09-03: the three themes are "a broad classification, now we need to narrow down
# within each class". Theme 3 (stock and equity) is the priority because it is the theme that
# speaks to high-skilled workers.
#
# Every setting below matches the parent run in run_disclosure_analysis.sh, so a second-level
# diagnostic is comparable to the first-level diagnostic of the same name.
set -euo pipefail

PY="${PY:-.venv/Scripts/python.exe}"
D=data/derived
FROZEN_QUEUE="$D/disclosure_frozen_queue.csv"
PARENT_TOPICS="$D/employee_topics_100"
PARENT_CORPUS="$D/employee_corpus_100"
SEED=20260823

# Theme 3 first: it is the one the advisor asked for by name.
for t in 3 1 2; do
  SUBCORPUS="$D/employee_corpus_100_t$t"
  SUBTOPICS="$D/employee_topics_100_t$t"

  echo "== topic_$t: build the sub-corpus =="
  $PY -m tag_edgar.cli build-topic-subset-corpus \
    "$PARENT_TOPICS/canonical_topic_assignments.csv" "$PARENT_CORPUS" \
    --parent-topic-id "topic_$t" --output-dir "$SUBCORPUS"

  echo "== topic_$t: fit the second level =="
  $PY -m tag_edgar.cli analyze-employee-topics "$FROZEN_QUEUE" "$SUBCORPUS" \
    --output-dir "$SUBTOPICS" --seed "$SEED" --k-min 3 --k-max 7 \
    --fit-balance source_family --max-fit-passages 1500
done

echo "Done. Second-level results in $D/employee_topics_100_t{3,1,2}"
