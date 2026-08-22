# Canonical enrichment history

Release RC1F6 now promotes accepted AI taxonomy suggestions into a provider-independent
`canonical_enrichments` store. The provider registry records where enrichment originated,
while the accepted value and provenance remain available even when the original runtime or
reference database is later removed.

Normal reversal is non-destructive. It changes the enrichment lifecycle from `active` to
`reversed`, closes its validity period, and changes the generated observation from confirmed
to unconfirmed by adding a new observation revision. Analyses, decisions, enrichments, and
observations remain available as the determination history.

Physical removal is intentionally not exposed through the review workflow. The schema
reserves `enrichment_purge_audit` for a future privileged purge service that must validate
scope, record a reason, and preserve an audit trail.
