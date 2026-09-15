# Unified platform bootstrap contract

Fieldora deployment targets must consume one validated bootstrap manifest rather than defining separate password, identity, monitoring, or update contracts per target.

## Scope

The contract covers the six first-class targets: Windows Desktop, Linux Desktop, Windows Docker, Linux Docker, Kubernetes, and OpenShift.

It defines bootstrap intent for Fieldora, FieldoraBastion, Keycloak, Wazuh, optional OpenKAT, external human identity brokers, service secrets, and the software supply-chain controls required for commercial private Fieldora releases.

Target-specific installers remain responsible for translating the validated manifest into native secret stores, service definitions, container or orchestration resources, certificates, storage, networking, and health checks. The manifest is not a permanent plaintext secret database.

## Trust boundaries

- Keycloak authenticates humans and brokers external identities. Fieldora remains authoritative for PBAC and application authorization.
- FieldoraBastion remains the secure package acquisition, quarantine, scan, verification, approval, broadcast, and collection boundary.
- Wazuh remains monitoring and correlation infrastructure. Monitoring failure must never weaken package-integrity acceptance rules.
- OpenKAT is optional posture and vulnerability-assessment infrastructure. It must not automatically approve packages, alter PBAC, or change identity policy.
- Cloud workload credentials remain separate from human identity federation. Prefer provider-native workload identity instead of long-lived AWS, Azure, or GCP keys in this manifest.

## Bootstrap secrets

A bootstrap manifest may contain initial administrator and service credentials inline when the operator explicitly chooses a single-file installation workflow. Inline secrets must be strong and are accepted only as bootstrap input.

Installers must restrict access to the file immediately, avoid printing or logging secret values, migrate secrets into the target-appropriate protected store, and offer secure deletion of the bootstrap file after successful provisioning. Kubernetes and OpenShift should use Secrets or an approved external secret provider; desktop and Docker targets need equivalent protected local storage rather than persistent plaintext `.env` files.

Environment-variable secret references are also supported for automated installation.

## Human identity brokers

When Keycloak is enabled, the manifest can declare human identity brokers for Microsoft Entra ID, Google, AWS-associated federation, generic OIDC, or SAML. These entries are authentication federation only. They must not grant Fieldora long-lived cloud infrastructure credentials.

## Software supply chain

Every validated manifest enables the approved update and release controls:

- Renovate for dependency and upstream-version discovery.
- Trivy for vulnerability scanning of dependencies, filesystems, deployment assets, and built images.
- Syft for release SBOM generation.
- OSV as an additional vulnerability-intelligence source.
- `commercial-private` license policy for automated review of third-party licensing.

An update finding does not directly create a production release. Routine, security, and major/breaking updates enter ordinary reviewable branches and pull requests, pass tests and deployment-target certification, generate an SBOM, pass vulnerability and license gates, and produce signed release artifacts.

Unknown, non-commercial, incompatible, or otherwise unapproved licensing must fail the release gate rather than silently entering a commercial Fieldora build. Use of independently deployed open-source services must not create an obligation to publish unrelated proprietary Fieldora or FieldoraBastion source.

## Update delivery

Approved Fieldora software and security updates may become a dedicated FieldoraBastion package class. Connected and air-gapped installations retain the same signed-manifest and independent-verification model before an authorized update collector installs the package.

## Example

The example below intentionally uses placeholders and must never be copied into production with unchanged credentials.

```json
{
  "schema_version": 1,
  "deployment_target": "linux-docker",
  "components": {
    "fieldora": {"enabled": true, "version": "5.4.0"},
    "bastion": {"enabled": true, "version": "approved"},
    "keycloak": {"enabled": true, "version": "approved"},
    "wazuh": {"enabled": true, "version": "approved"},
    "openkat": {"enabled": false, "version": "approved"}
  },
  "administrators": {
    "fieldora": {"username": "admin", "password": {"source": "environment", "name": "FIELDORA_ADMIN_PASSWORD"}},
    "keycloak": {"username": "kc-admin", "password": {"source": "environment", "name": "KEYCLOAK_ADMIN_PASSWORD"}},
    "wazuh": {"username": "wazuh-admin", "password": {"source": "environment", "name": "WAZUH_ADMIN_PASSWORD"}}
  },
  "secrets": {
    "fieldora_service": {"source": "environment", "name": "FIELDORA_SERVICE_SECRET"},
    "bastion_service": {"source": "environment", "name": "FIELDORA_BASTION_SERVICE_SECRET"}
  },
  "identity": {
    "brokers": [
      {
        "provider": "entra",
        "client_id": "fieldora",
        "client_secret": {"source": "environment", "name": "FIELDORA_ENTRA_CLIENT_SECRET"}
      }
    ]
  },
  "supply_chain": {
    "renovate": true,
    "trivy": true,
    "syft": true,
    "osv": true,
    "license_policy": "commercial-private"
  }
}
```

The initial implementation validates this contract in `natureai_next.bootstrap.platform_manifest`. Subsequent target-specific installer changes should depend on that validator rather than inventing separate component or secret schemas.
