# Production incident response

1. Declare the incident, assign an incident commander, preserve UTC timestamps, and
   start an append-only event log.
2. Classify affected tenants, projects, credentials, data classes, services, and
   regions. Do not infer that a service outage implies no disclosure.
3. Contain with ingress rules, credential/version rotation, session revocation, worker
   pause, or tenant isolation. Preserve legal holds and audit evidence.
4. Verify the PBAC boundary through APIs, objects, search, exports, jobs, and restored
   data before reopening traffic.
5. Recover from a known release and verified backup. Validate checksums, database
   consistency, object inventory, search rebuilding, and audit-chain continuity.
6. Notify authorized stakeholders according to the applicable contract and law.
7. Record root cause, timeline, affected scope, remediation, and follow-up exercises.

Never delete suspected evidence, disable tenant scoping, expose a direct object URL, or
restore production over the only existing copy during incident handling.
