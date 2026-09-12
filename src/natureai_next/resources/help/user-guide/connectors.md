# Connectors

Connectors register governed integrations with external or local systems. Each connector records its version, endpoint, network classification, capabilities, enabled state, and health information.

## Configure a connector

Confirm the connector endpoint and network boundary before enabling it. Declare only the capabilities the integration actually provides, and keep version information current so operators can identify incompatible or outdated deployments.

## Security

Connector administration is capability-gated. Do not place passwords, API keys, or other secrets in names, endpoints, or capability descriptions. Enabling a connector does not bypass Fieldora authorization or purpose controls.
