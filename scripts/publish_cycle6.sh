#!/usr/bin/env bash
# Publish the cycle-6 result tables into data/published/disclosure_sample_134/.
#
# Why this is a script and not three commands typed by hand. Every publish script accepts the
# cycle-specific paths and every one of their defaults points at cycle 5. Twice in this cycle a
# caller passed some of the paths and let the rest default, and the output was not an error but a
# report carrying the previous cycle's numbers under this cycle's heading -- see the 2026-09-04
# commits and docs/retrieval_window_memo.md section 5d. Setting the paths once, here, is the fix
# that survives being run by someone in a hurry.
#
# Order matters. publish_disclosure_snapshot.py regenerates the directory README from whatever
# files it finds, so the two companion scripts must write their tables BEFORE it runs, or the
# README silently omits them and a reader concludes they were withdrawn.
#
# Usage:  bash scripts/publish_cycle6.sh
set -euo pipefail

PY="${PY:-.venv/Scripts/python.exe}"
D=data/derived

CORPUS="$D/employee_corpus_c6"
TOPICS="$D/employee_topics_c6"
FROZEN="$D/disclosure_frozen_sample_c6"
LABELS="$D/deal_ai_labels_c6"
TONE="$D/employee_tone_c6"
REPORT="docs/disclosure_sample_report_c6.md"
OUT="${OUT:-data/published/disclosure_sample_134}"

# Cross-check before writing anything. Every defect in this cycle had the same shape: nothing
# failed, and a wrong number printed under a correct-looking heading. All were caught by hand, by
# reading one number against another that should have agreed with it. These two agreements are
# cheap enough to check on every run.
#
#   1. The report's reproduction section names the directory a reader should check its numbers
#      against. That string was hardcoded to the cycle-5 path, so the cycle-6 report sent readers
#      to the superseded tables while every number above it was correct.
#   2. The report's headline passage count must be the one the passage tables are built from. A
#      report written against another cycle's frozen sample is not an error at any step; it just
#      prints last cycle's totals.
echo "== 0/3 check the report agrees with what is about to be published =="
if ! grep -q "$OUT" "$REPORT"; then
  echo "FAIL: $REPORT does not name $OUT." >&2
  echo "      Regenerate it with --published-dir '$OUT/' before publishing." >&2
  exit 1
fi
REPORT_PASSAGES=$(grep -oE '\*\*[0-9]{2,3},[0-9]{3}\*\* employee passages|[0-9]{2,3},[0-9]{3} passages drawn' "$REPORT" | grep -oE '[0-9]{2,3},[0-9]{3}' | head -1)
FROZEN_PASSAGES=$($PY -c "
import csv,sys
csv.field_size_limit(10**9)
rows=list(csv.DictReader(open(r'$FROZEN/frozen_sample.csv',newline='',encoding='utf-8')))
print(f\"{sum(int(r['included_passages']) for r in rows if r['sample_status']=='modelled'):,}\")
")
if [ "$REPORT_PASSAGES" != "$FROZEN_PASSAGES" ]; then
  echo "FAIL: report headline says $REPORT_PASSAGES passages; the frozen sample carries $FROZEN_PASSAGES." >&2
  echo "      That is the cycle-mismatch defect. Regenerate the report from all-cycle-6 inputs." >&2
  exit 1
fi
echo "report names $OUT; headline $REPORT_PASSAGES passages matches the frozen sample"
echo

echo "== 1/3 deal profiles =="
$PY scripts/build_deal_profiles.py \
  --frozen-sample "$FROZEN/frozen_sample.csv" \
  --deal-topic-matrix "$TOPICS/deal_topic_matrix.csv" \
  --ai-labels "$LABELS/deal_ai_labels.csv" \
  --output-dir "$OUT"

echo "== 2/3 passage links =="
$PY scripts/publish_passage_links.py \
  --topics-dir "$TOPICS" \
  --corpus-dir "$CORPUS" \
  --frozen-sample "$FROZEN/frozen_sample.csv" \
  --output-dir "$OUT"

echo "== 3/3 snapshot and README (last: the README lists what the two above wrote) =="
$PY scripts/publish_disclosure_snapshot.py \
  --corpus-dir "$CORPUS" \
  --topics-dir "$TOPICS" \
  --frozen-dir "$FROZEN" \
  --ai-labels-dir "$LABELS" \
  --tone-dir "$TONE" \
  --report "$REPORT" \
  --output-dir "$OUT"

echo
echo "Published to $OUT"
echo "Still to do by hand:"
echo "  - add the superseded pointer to data/published/disclosure_sample_133/README.md"
echo "  - point NAVIGATION.md at the new snapshot"
