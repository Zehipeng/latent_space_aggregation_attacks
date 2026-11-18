# Reviewer selection/mechanism protocol v1.0: 50-key budget addendum

## Scope

This is a time-bounded supplementary execution profile of
`reviewer_selection_mechanism_v1.0`. It does not replace the 200-key main
forgery/removal experiments and must not be reported as a 200-key formal run.

The profile freezes the first 50 preregistered key identifiers (`key_000` through
`key_049`) before observing E2/E4 outcomes. It retains the complete factorial
design: two model settings, three watermark methods, two tasks, all four
reference-selection strategies, 150 optimization steps, and every E4 control.
The resulting scale is 2,400 attacks and 19,200 candidate images.

## Candidate-bank reuse

Candidate images may be reused from the interrupted 200-key run only when the
source run identity is valid and every selected unit contains all 64 candidate
indices with matching per-image SHA-256 hashes. Reuse creates hard links (or
verified copies when requested) in a new run directory. It never edits the
source run. The destination preparation phase revalidates all units and records
the reuse provenance.

## Evidence boundary

All per-condition estimates, Wilson intervals, paired comparisons, and clustered
bootstrap analyses use 50 key clusters. The wider uncertainty relative to the
200-key protocol must remain visible. This profile is supplementary evidence for
reference-selection sensitivity and mechanism association, not a replacement for
the 200-key primary results.
