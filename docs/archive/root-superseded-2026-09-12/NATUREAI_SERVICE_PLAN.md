# Fieldora NatureAI service plan

Status: PROPOSED — implementation slice after the current managed-web parity defects are corrected and certified.

## Goal

Provide one optional, separately deployable NatureAI service that Fieldora can use for biological AI inference and external biodiversity reference data without embedding model-specific runtimes or third-party credentials in the Fieldora API/server.

Fieldora remains authoritative for evidence identity, provenance, observations, projects, expert determinations, PBAC, audit, and accepted scientific conclusions. NatureAI is a governed compute/data adapter. It never owns Fieldora evidence or silently writes accepted identifications.

## Trust boundary

- Browser and desktop clients call Fieldora, never NatureAI directly.
- `fieldora-natureai` receives a durable enrolled service identity and mTLS certificate.
- Fieldora independently authorizes every user-facing AI/data action before requesting NatureAI work.
- NatureAI receives opaque Fieldora identifiers and bounded media bytes/derivatives; it does not receive filesystem paths, object-store/provider references, storage credentials, organization IDs, policy names, denial reasons, or unrestricted database access.
- Model output is a candidate determination with provenance, never an accepted scientific conclusion.
- Sharing/association does not rewrite evidence identity, creator/source provenance, or ownership.
- Third-party credentials (for example GBIF download credentials) are service-side secrets and are never returned to clients or recorded in result payloads/audit details.

## Deployment shape

Initial deployment uses one optional container:

`fieldora-server -> mTLS -> fieldora-natureai -> model adapters / external biodiversity APIs`

The first image should be CPU-capable. GPU is an optional Compose profile/device allocation. Model files are mounted read-only and are not downloaded automatically by the reference deployment. Existing Fieldora offline-model signature/hash/clean-scan rules apply to model installation.

If future models require incompatible CUDA/runtime stacks, NatureAI may route to separate inference workers without changing the Fieldora-facing contract.

## Provider registry

NatureAI exposes providers through capabilities rather than UI-specific model names. Initial capability vocabulary:

- `image_embedding`
- `image_taxon_ranking`
- `zero_shot_taxon_ranking`
- `camera_trap_detection`
- `camera_trap_classification`
- `trait_prediction`
- `reference_taxonomy_search`
- `occurrence_context`
- `occurrence_download`

Candidate model adapters:

1. BioCLIP
2. BioCLIP 2 / compatible later BioCLIP checkpoints
3. camera-trap / wildlife classification adapter (provider implementation chosen separately)

A model registration records at minimum provider/model ID, version, immutable artifact digest, declared capabilities, runtime/device requirements, enabled state, and health. No host/model filesystem path is exposed through Fieldora APIs.

## Candidate determination contract

A NatureAI inference result contains safe scientific provenance such as:

- opaque request/job ID
- opaque Fieldora evidence ID supplied for correlation
- model/provider ID and version
- immutable model artifact digest
- inference capability
- generated timestamp
- ranked candidate taxon identifiers/names and model scores
- optional normalized taxonomic references

Fieldora persists this as an AI-generated candidate/determination linked to the governed evidence. Expert acceptance/rejection/supersession remains an explicit governed Fieldora action and preserves history.

Occurrence/reference context must remain distinct from model confidence. For example, a nearby GBIF occurrence can be displayed as occurrence context but must not silently increase or rewrite the model score.

## GBIF connector

NatureAI provides two GBIF modes:

### Interactive reference lookup

Use public GBIF APIs for bounded taxonomy and occurrence-context queries. Responses are normalized into a safe NatureAI reference contract before returning to Fieldora.

### Governed dataset acquisition

Large occurrence acquisition is asynchronous. NatureAI submits a bounded GBIF occurrence download request using service-side credentials, records the returned download key, polls status, retrieves the completed archive, verifies the retrieved artifact, and hands it to Fieldora's governed dataset/intake workflow.

Fieldora records source/provenance including the normalized request, GBIF download key, DOI when available, retrieval time, artifact digest, relevant license/citation metadata, and resulting governed dataset identity. Imported GBIF records do not become organization-authored observations merely because they were imported.

The first implementation should support established predicate downloads and DWCA/SIMPLE_CSV as needed. Experimental GBIF SQL downloads are not required for the initial contract.

## Initial internal API

The Fieldora-facing API should be narrow and versioned:

- `GET /health/live`
- `GET /health/ready`
- `GET /v1/providers`
- `POST /v1/inference/image`
- `POST /v1/inference/batch`
- `GET /v1/jobs/{job_id}`
- `GET /v1/taxa/search`
- `GET /v1/occurrences/context`
- `POST /v1/gbif/downloads`
- `GET /v1/gbif/downloads/{job_id}`

Large/batch work is asynchronous. Request bodies are bounded. Error payloads use stable safe codes/correlation IDs and do not disclose internal routing or storage details.

## Fieldora integration

Knowledge & AI should eventually expose:

- available model/provider capabilities;
- create inference/enrichment task;
- candidate determinations with model/version provenance;
- explicit expert accept/reject/supersede actions;
- job state and safe failure information.

Administration may expose provider health, enabled capabilities, model version/digest, CPU/GPU readiness, and GBIF connector health. It must not expose service secrets or storage/model host paths.

## Implementation slices

### NAI-001 — service contract and threat boundary

Define request/result schemas, provider capability registry, bounded payload rules, mTLS identity, safe errors, and tests proving no storage/auth/policy internals leak.

### NAI-002 — minimal Docker service

Add `fieldora-natureai` with liveness/readiness, non-root runtime, read-only model mount, durable service enrollment/mTLS, resource limits, CPU default and optional GPU profile. The normal Fieldora stack remains healthy when NatureAI is absent/disabled.

### NAI-003 — Fieldora governed client

Add server-side NatureAI client/job adapter. Browser never receives the NatureAI endpoint. PBAC is checked by Fieldora independently. Timeouts/retries are idempotent and bounded.

### NAI-004 — model registry and BioCLIP adapter

Implement provider discovery plus a BioCLIP-family image/taxon-ranking adapter. Persist model version and immutable artifact digest with every result. No automatic model download.

### NAI-005 — GBIF reference connector

Implement bounded taxon search and occurrence context with caching/rate-limit handling and source metadata.

### NAI-006 — GBIF governed download

Implement asynchronous predicate downloads, status polling, archive verification, DOI/license/citation capture, and handoff to Fieldora governed dataset intake.

### NAI-007 — candidate determination integration

Persist NatureAI output as AI candidate determinations linked to existing evidence. Expert acceptance remains a separate governed Fieldora action. Add zero-trust and provenance regression tests.

### NAI-008 — camera-trap provider

Add a camera-trap detection/classification adapter behind the same provider interface. Provider choice/model licensing/deployment requirements must be documented before bundling artifacts.

### NAI-009 — runtime certification

Certify CPU deployment, optional GPU deployment where available, service mTLS, provider failure isolation, model digest provenance, GBIF job recovery, browser zero-trust behavior, and clean uninstall/disable behavior.

## Acceptance invariants

1. NatureAI failure or absence cannot make core Fieldora evidence inaccessible.
2. AI output never silently becomes an accepted identification.
3. Every persisted AI result identifies the exact model/version/artifact digest used.
4. External biodiversity records preserve external source/citation/license provenance.
5. GBIF context and AI confidence remain separate evidence channels.
6. No browser can call NatureAI directly in the reference deployment.
7. NatureAI has no unrestricted Fieldora database/storage access.
8. Model bytes are installed through verified offline-model mechanisms and mounted read-only.
9. No third-party credential, filesystem path, provider routing secret, organization ID, or policy metadata appears in browser/API output.
10. Batch retries cannot create duplicate determinations or duplicate governed datasets.
