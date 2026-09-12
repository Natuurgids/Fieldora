# Web parity slice issue template

Use this template when a parity item is large enough to deserve a separate GitHub issue. The canonical status remains in `WEB_PARITY_STATUS.md` and `WEB_DESKTOP_PARITY_PLAN.md`.

## Parity ID

`WEB-___`

## Desktop contract

- Desktop module/service:
- Domain/application service:
- Expected behavior:

## Current web behavior

- Web control/route:
- Observed mismatch:

## Intended shared contract

Describe the common domain/application behavior. Presentation differences are allowed; scientific/governance semantics are not.

## Acceptance tests

- [ ] Domain/application test
- [ ] API test
- [ ] Chromium browser test
- [ ] Firefox browser test where relevant
- [ ] WebKit browser test where relevant
- [ ] PostgreSQL parity test where persistence/concurrency is involved
- [ ] PBAC/zero-trust denial test where mutation/disclosure is involved

## Certification

Named workflow/run:

## Notes / follow-up

Record intentionally deferred behavior here instead of silently broadening the slice.
