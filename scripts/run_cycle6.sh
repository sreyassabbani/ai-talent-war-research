#!/usr/bin/env bash
# Cycle 6: the same pipeline as cycle 5, on a corpus whose deduplication key no longer includes
# the heading.
#
# Why a rerun at all. Cycle 5 modelled one paragraph twice whenever an exhibit and the S-4 or
# proxy reprinting it disagreed about its heading -- 968 excess rows, 7.0% of the 133-deal
# sample, and over 20% in three deals. The same heading text was also being fed to the model as
# features, 2,254 passages of it reading "Table of Contents". Both are fixed in
# src/tag_edgar/employee_corpus.py; docs/retrieval_window_memo.md sections 5a and 5b record the
# measurement and correct the earlier, wrong diagnosis.
#
# This script sets paths and calls the cycle-5 scripts unchanged. Nothing here forks the
# analysis: if cycle 6 differs from cycle 5 it is because the corpus differs, which is the only
# comparison worth being able to make.
#
# The cycle-5 outputs are left exactly where they are. data/published/disclosure_sample_133/
# stays as the superseded published record.
#
# Usage:  bash scripts/run_cycle6.sh
#         SKIP_CORPUS=1 bash scripts/run_cycle6.sh    # corpus already built
set -euo pipefail

PY="${PY:-.venv/Scripts/python.exe}"
D=data/derived

export CORPUS="$D/employee_corpus_c6"
export TOPICS="$D/employee_topics_c6"
export FROZEN_SAMPLE="$D/disclosure_frozen_sample_c6"
export FROZEN_QUEUE="$D/disclosure_frozen_queue_c6.csv"
export LABELS="$D/deal_ai_labels_c6"
export TONE="$D/employee_tone_c6"
export REVIEW="$D/employee_topic_review_c6"
export REPORT="docs/disclosure_sample_report_c6.md"

echo "### cycle 6, first level"
bash scripts/run_disclosure_analysis.sh

echo "### cycle 6, second level"
bash scripts/run_topic_subsets.sh

echo "Done. Compare against cycle 5 with: $PY scripts/compare_cycles.py"
