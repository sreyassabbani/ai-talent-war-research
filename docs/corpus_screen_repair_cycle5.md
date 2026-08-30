# Corpus-screen repair cycle 5

The completed 150-row human relevance audit remains a failed historical gate: it is not altered
or rescored by this repair. Its error patterns motivated this prespecified next screen version.

## Changes

- Exclude short employee-labelled captions that contain no operative action.
- Exclude table-of-contents and exhibit-navigation fragments unless they contain employee-treatment
  language.
- Recognize forfeiture, termination, and effective-time language as equity-award treatment, so
  substantive award provisions are not discarded as generic term hits.

## Rebuilt artifacts

The repaired cached pilot corpus is in `data/derived/employee_corpus_cycle5/`. It contains 2,331
included and 3,219 excluded candidates from the unchanged 5,550-passage screening universe.

`data/derived/corpus_relevance_audit_cycle5/` is a newly prepared, blinded 75-included and
75-excluded packet. Its status is `pending`: it requires a fresh human assessment before any claim
that the repair passed the prespecified relevance/recall gate.
