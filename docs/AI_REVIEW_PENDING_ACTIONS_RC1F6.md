# AI Review pending-row actions — RC1F6

## Accept

Accepts the selected pending suggestion, creates its observation and canonical enrichment, changes its review state to `accepted`, refreshes queue counts, and remains on the current photograph.

## Accept All Pending & Next

Atomically selects every suggestion for the current photograph whose review state is exactly `pending`. Each selected row is accepted and receives its own canonical enrichment. Existing accepted, rejected, deferred, reversed, and superseded history is not changed. The workspace then advances to the next photograph containing a pending suggestion.

## Accept Only & Next

Accepts the selected pending suggestion and rejects every other suggestion for the photograph whose review state is exactly `pending`. Existing accepted, rejected, deferred, reversed, and superseded history is not changed. The workspace then advances to the next photograph containing a pending suggestion.

## Data rule

Accepted taxonomy enrichment is multi-valued for a photograph because a photograph may contain multiple valid detections. New acceptances do not implicitly supersede other active accepted enrichment. Supersession and reversal remain explicit historical actions.

## Label-only BioCLIP suggestions

A valid BioCLIP suggestion may not yet resolve to a taxon in the installed taxonomy. Accepting such a row changes it to **accepted** and stores canonical Aperture-owned enrichment. Aperture creates a confirmed observation only when the suggestion is linked to an actual taxonomy record.
