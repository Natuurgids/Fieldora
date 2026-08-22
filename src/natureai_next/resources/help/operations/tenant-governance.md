# Tenant governance operations

Use `fieldora-governance` from an authenticated administrator environment. Production
commands should use `--backend postgresql --postgres-dsn-file ...`; the DSN file must
come from the external-secret provider and must not be copied into reports or logs.

Set or revise a quota:

```text
fieldora-governance --backend postgresql --postgres-dsn-file /run/secrets/postgresql-dsn \
  quota-set --organization tenant-a --metric api_requests --limit 100000 \
  --period-seconds 3600 --expected-revision 3
```

Generate a tenant-scoped usage and cost report:

```text
fieldora-governance --backend postgresql --postgres-dsn-file /run/secrets/postgresql-dsn \
  usage-report --organization tenant-a --start-epoch 1785283200 \
  --end-epoch 1785369600 --unit-costs metric-prices.json
```

The price file is a JSON object whose values are non-negative decimal strings, for
example `{"export_bytes":"0.00000001","jobs":"0.25"}`. Missing metrics use zero cost.
Reports never combine organizations. Changes should use the last observed revision;
a stale revision fails instead of overwriting a concurrent administrator.
