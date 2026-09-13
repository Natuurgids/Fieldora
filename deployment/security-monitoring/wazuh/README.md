# Wazuh security monitoring integration

Fieldora can emit bounded security events as single-line JSON for collection by a Wazuh agent or manager. Wazuh is monitoring and correlation infrastructure; it does not replace FieldoraBastion quarantine, malware scanning, signed approval, or Fieldora trusted-side verification.

## Event path

Configure `WazuhJsonlSink` with an operator-controlled, pre-created log path such as `/var/log/fieldora/security-events.jsonl`. Fieldora never creates the parent directory and never writes package contents or internal package paths to this event stream.

Configure Wazuh `localfile` collection with JSON parsing:

```xml
<localfile>
  <location>/var/log/fieldora/security-events.jsonl</location>
  <log_format>json</log_format>
  <label key="@source">fieldora</label>
</localfile>
```

The same contract applies on desktop, Docker, Kubernetes, and OpenShift deployments. The concrete log mount, Wazuh agent placement, credentials, certificates, retention, and network policy are deployment-target concerns and must be supplied by the operator. Do not embed Wazuh administrative credentials in Fieldora configuration.

For containerized deployments, mount only the security-event directory needed by the collector. Do not mount Docker/Podman/OpenShift sockets, Fieldora databases, Bastion quarantine storage, or signing keys into the monitoring component.

For Kubernetes and OpenShift, prefer an operator-managed Wazuh agent/collector and a narrowly scoped shared logging mechanism or platform log collection. Keep the Wazuh central server, indexer, and dashboard lifecycle separate from Fieldora application credentials.
