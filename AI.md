## Aperture V3.RC1F1 NatureAI engine

NatureAI is installed as a complete classification engine: BioCLIP v1, pybioclip, TreeOfLifeClassifier, and its matching Tree-of-Life labels and embeddings. The default classifier works without a CSV or GBIF. GBIF is an optional independent resolver and enrichment source. Readiness requires the model, runtime, classifier, resource cache, and activation record to validate together; an empty Aperture prompt set is not considered ready.

## Photograph-level suggestion resolution (0.15.2)

Suggestions remain immutable evidence records, but their review states can be resolved as a photograph-level set. Accepting one candidate and rejecting its alternatives is committed in one database transaction, including observation creation and audit/outbox records.

# NatureAI Next — AI Design

**Status:** Approved design baseline  
**Document version:** 0.1

## 1. Purpose and principles

AI assists organization, discovery, and identification while keeping the user in control. All inference is local. AI output is advisory unless explicitly accepted by the user.

Principles:

1. no cloud inference or remote image processing;
2. reproducible, provenance-rich results;
3. provider-independent application contracts;
4. bounded use of GPU, CPU, RAM, and storage;
5. graceful CPU fallback;
6. model outputs separated from confirmed metadata;
7. transparent limitations and no false claim of scientific certainty.

## 2. Initial capabilities

### 2.1 Image embeddings

BioCLIP produces normalized image embeddings used for:

- visual similarity search;
- text-to-image search through compatible text embeddings;
- clustering and collection exploration;
- candidate retrieval before detailed classification;
- duplicate and near-duplicate assistance.

### 2.2 Zero-shot classification

The system compares image embeddings with curated prompt ensembles for candidate labels. Zero-shot output is suitable for broad groups and candidate ranking, not automatic authoritative identification.

### 2.3 Taxon candidate ranking

Candidate generation is constrained by:

- active taxonomy;
- selected geographic region where known;
- date/season where a plugin or calibrated model supports it;
- user-selected organism group;
- model-supported label vocabulary.

Geography and season are ranking signals, not hard exclusions by default, because vagrants, cultivated species, captive organisms, and incorrect metadata occur.

### 2.4 Similarity search

Queries may originate from:

- an existing asset;
- a selected crop/region;
- text prompts;
- a set of positive and negative examples.

Search results state the model variant used. Embeddings from incompatible variants are never compared.

## 3. Model abstraction

The application depends on an `AIEngine` port with operations conceptually equivalent to:

- inspect capabilities;
- load/unload model variant;
- embed images;
- embed text;
- classify against label sets;
- estimate resource requirements;
- report provider diagnostics.

The port exchanges typed arrays or serializable result objects, not Torch tensors across application boundaries.

Model providers implement:

- Torch CUDA;
- Torch CPU;
- ONNX Runtime CUDA or CPU where validated;
- future Intel NPU provider.

## 4. Model package format

A model package is a local directory or signed archive containing:

- manifest with model ID and semantic version;
- model family and upstream source;
- license and attribution;
- artifact files and SHA-256 checksums;
- supported providers and precision modes;
- expected input size and normalization;
- preprocessing identity and version;
- embedding dimension and normalization behavior;
- label/prompt resources where applicable;
- minimum application and plugin API versions;
- optional calibration package references;
- regression fixture fingerprints.

Model installation stages files, verifies checksums and signatures, then atomically activates the package. A failed update leaves the previous package usable.

## 5. BioCLIP baseline

BioCLIP is the initial foundation model, integrated through a dedicated provider adapter. The adapter owns all BioCLIP-specific preprocessing, prompt formatting, model loading, and output normalization.

Application services must not assume:

- a fixed embedding dimension;
- a fixed image resolution;
- a fixed tokenizer;
- a particular Torch module structure;
- a fixed label set.

These values come from the validated model manifest.

## 6. Preprocessing

Preprocessing is part of model identity. It includes:

- EXIF orientation correction;
- color conversion;
- crop/resize policy;
- interpolation method;
- tensor normalization;
- alpha handling;
- bit-depth conversion;
- optional multi-crop policy.

Any preprocessing change increments the preprocessing identity and invalidates dependent embeddings and indexes. Original files remain untouched.

## 7. Inference execution

### 7.1 Device selection

Default provider order on the reference system:

1. validated CUDA provider;
2. validated ONNX CUDA provider if selected for that model;
3. CPU provider.

Provider selection considers availability, model compatibility, user preference, VRAM budget, and prior failure state.

### 7.2 Precision

- FP16 may be used on CUDA when regression tests confirm acceptable output tolerance.
- FP32 is the correctness baseline.
- Quantized variants require their own manifest, validation, and provenance identity.
- Precision is never changed silently within an inference run.

### 7.3 Batching

The AI worker determines batch size from:

- model manifest estimates;
- available VRAM;
- configured VRAM reservation;
- image dimensions after preprocessing;
- observed out-of-memory failures.

A batch failure caused by memory may retry with a smaller batch. The retry is recorded. Individual corrupt images fail independently.

### 7.4 Model residency

Only a bounded set of models may remain loaded. Default policy keeps the active embedding model resident while AI work is active and unloads it after a configurable idle period. UI browsing does not require model load.

### 7.5 Cancellation

Cancellation occurs between batches and at safe preprocessing checkpoints. GPU kernels already submitted may complete, but their results are discarded if the job is cancelled before commit.

## 8. Prompt and label management

Prompt sets are versioned resources. A label entry contains:

- canonical label ID;
- text templates;
- language;
- optional taxon mapping;
- organism group;
- provenance and author;
- version.

Prompt ensembling averages or otherwise combines text embeddings according to a documented strategy. Prompt changes create a new prompt-set identity and inference run.

Taxon names are not blindly converted to prompts. Scientific and vernacular names may have different templates and weights.

## 9. Confidence and review

### 9.1 Scores

Raw similarity logits or cosine scores are stored as raw scores. UI labels such as “high”, “medium”, and “low” require documented thresholds specific to model, task, and prompt set.

A score may be displayed as a probability only when a calibration artifact identifies:

- model variant;
- task;
- candidate universe;
- calibration dataset;
- calibration method;
- validation metrics;
- version.

### 9.2 Open-set behavior

The system must support “unknown” and “insufficient confidence.” It must not force a best taxon when evidence is weak.

Candidate review shows:

- top candidates;
- raw or calibrated score type;
- model and version;
- geographic context used;
- crop used;
- warnings for unsupported groups or low confidence.

### 9.3 Metadata precedence

Priority order:

1. current user-confirmed metadata;
2. explicitly imported authoritative metadata marked confirmed;
3. accepted plugin result;
4. pending AI suggestion;
5. unreviewed imported hint.

AI never overwrites levels 1–3 without an explicit review command.

## 10. Candidate pipeline

A standard taxon suggestion pipeline:

1. validate asset and decode image;
2. select full image or regions of interest;
3. generate or retrieve compatible embedding;
4. predict broad group using curated labels;
5. retrieve candidate taxa from active taxonomy and regional context;
6. generate text embeddings or retrieve cached label embeddings;
7. rank candidates;
8. apply optional calibrated reranker plugin;
9. persist suggestions and provenance;
10. notify the review workspace through committed events.

Each stage is independently versioned and observable.

## 11. Embedding lifecycle

- Embeddings are immutable for a given asset content hash, crop, model variant, and preprocessing identity.
- A changed original hash or crop invalidates compatibility.
- User metadata changes do not invalidate visual embeddings.
- Model removal is blocked while its embeddings are configured as active unless the user chooses to remove or orphan dependent data.
- Re-embedding is a resumable persistent job.

## 12. Vector search

The vector index is an acceleration cache. Requirements:

- cosine or model-declared metric;
- model-specific index;
- deterministic filtering by active asset state;
- post-filter support for taxonomy, location, rating, date, and collection;
- exact-search fallback;
- background rebuild with atomic activation;
- result provenance including model identity and index generation.

For highly selective structured filters, the planner may filter relational candidates first and perform exact vector scoring on the subset.

## 13. Near-duplicate assistance

Duplicate detection has separate levels:

- exact duplicate: same SHA-256;
- likely file duplicate: fast fingerprint and metadata agreement, requiring canonical hash confirmation;
- visual near-duplicate: perceptual hash and/or embedding similarity;
- burst similarity: close capture time plus visual similarity.

Only exact hashes may drive automatic deduplication policy. Near-duplicate results are review suggestions.

## 14. Training and fine-tuning

The first stable release does not require model training. The architecture permits future local adapters or fine-tuned classifiers through model packages and plugins.

Any future training feature must define:

- dataset consent and provenance;
- reproducibility;
- checkpoint storage;
- evaluation split;
- overfitting safeguards;
- hardware resource control;
- export and removal.

## 15. AI diagnostics

Diagnostics report locally:

- detected CUDA and driver capability;
- Torch and ONNX provider versions;
- device name and memory;
- installed model manifests;
- last load/inference error;
- benchmark results on bundled non-user fixtures;
- current cache and index state.

Diagnostics never upload user images or metadata.

## 16. AI testing

- preprocessing golden tests;
- embedding shape, normalization, and deterministic tolerance tests;
- CPU/CUDA parity within documented tolerance;
- batch versus single-image parity;
- out-of-memory fallback tests;
- corrupt image isolation;
- model manifest validation;
- suggestion provenance tests;
- vector index exact-recall benchmark;
- UI review-state contract tests.

## 17. AI decisions

### AI-001: BioCLIP as initial provider, not core dependency

BioCLIP is the first adapter; application contracts remain model-independent.

### AI-002: Suggestions separated from confirmed data

Preserves user authority and inference provenance.

### AI-003: Preprocessing belongs to model identity

Prevents invalid reuse of embeddings after pipeline changes.

### AI-004: ANN index is a cache

SQLite embeddings preserve recoverability and permit exact fallback.

### AI-005: No uncalibrated probabilities

Raw scores must not be misrepresented as confidence probabilities.

## Desktop review boundary (0.13.0)

The production desktop now consumes the existing provider-independent suggestion and review contracts. It displays local BioCLIP package, model variant, prompt set, inference provenance, calibrated/raw scores, and review state. The desktop does not own model execution or SQLite and does not merge suggestions into catalog taxonomy implicitly. Inference generation remains an offline job/runtime concern; the review surface handles evidence already persisted by those services.


## Local suggestion generation (0.13.2)

The AI Review workspace exposes an explicit **Generate selected** command. The command consumes stable public IDs from the current Library selection, resolves the active signed local model package and compatible active prompt set, validates that taxonomy text embeddings are present for the active variant, and performs all inference locally. Each run is persisted in `inference_runs`; ranked outputs are immutable `ai_suggestions` with complete provenance. Per-asset failures are isolated and cancellation is cooperative. Human-confirmed observations remain separate and can only be created through review acceptance.

## Local AI resource management

AI Review exposes **Manage local AI resources…**. Model and taxonomy packages remain signed and are accepted only with an explicitly selected trusted-key JSON file. Prompt sets are validated and activated locally. Taxonomy text embeddings are generated only on explicit user request with the active local model and taxonomy release.

## Offline resource packaging

NatureAI Next 0.13.4 adds the `natureai-next-resources` boundary for reproducible, user-controlled creation and verification of signed local model and taxonomy packages. Third-party weights and taxonomy datasets are not bundled. The user obtains them under their upstream licenses, verifies provenance, and packages them locally using an explicitly managed Ed25519 signing identity. Prompt manifests are validated separately because they contain no executable or binary payload.

## Reproducible local resource workspace

`natureai-next-resources workspace-init` creates an explicit local resource tree and records absolute artifact paths in build configuration. This keeps acquisition, signing, verification, and installation reproducible without bundling third-party weights or private signing keys.

## Regional knowledge profiles (0.14.0)
Each library can select a primary continent, priority countries, preferred display languages, and a global fallback. AI Review resolves installed taxonomy occurrence records in this order: selected country, selected continent, rest of world. Regional evidence remains separate from BioCLIP visual confidence and never hides a visual candidate.

## Automatic regional acquisition (0.14.1)
Regional setup can explicitly retrieve GBIF occurrence evidence and Backbone Taxonomy details, build a locally signed taxonomy package, generate BioCLIP prompts, and build embeddings. Downloads never include photographs and run only after user confirmation.

## Personal observation context

AI Review queries confirmed observation history for each candidate taxon. First-observation status and previous counts never modify model confidence and remain a separate evidence layer.

## Ecological context

NatureAI displays locally installed conservation, seasonal, migration, and habitat evidence separately from BioCLIP confidence and regional occurrence. These fields are informational and never silently confirm or reject a suggestion.

## Version 2 asset enrichment model

AI engines enrich photos through immutable `asset_analyses` records. Each run is associated with one asset and retains engine, model/version, configuration, timestamps, source hash, status, and a compact summary. Taxon candidates and tags are normalized child records.

A newer model run does not erase an older result. Human acceptance creates a traceable promotion to an observation while preserving the original AI output. Large rebuildable artifacts stay outside the core library under the modular subsystem rules.

## BioCLIP analysis integration (Version 2 M5.2)

Local BioCLIP suggestion generation now creates one immutable asset-analysis record per processed photo. The analysis starts before preprocessing and inference, records the active model, version, variant, prompt set, execution provider, device, precision, and configuration, and ends in a succeeded or failed state.

Generated review suggestions retain their existing workflow and additionally reference the parent analysis. The same ranked results are preserved as normalized analysis taxon candidates, allowing photo enrichment history to remain available independently of the review queue. Historical suggestions created before this integration remain supported with a null analysis link.


## Build 3.321 RC3 update

GBIF Darwin Core taxonomy import is separate from model installation; offline PMTiles use a glyph-independent local street style; and BioCLIP downloads resume from persistent partial files after remote disconnects.

## Fieldora AI Platform (R23)

Fieldora now includes a provider-neutral AI chat and MCP integration layer. Existing Fieldora AI models and workflows remain available. LM Studio, Ollama, Hermes-hosting runtimes, and other OpenAI-compatible endpoints are additional configurable providers rather than replacements.

The default policy is offline-only. Local providers and local MCP servers can operate without outbound access. LAN or internet providers and internet-capable MCP servers require both global network mode to be enabled and an explicit administrator approval. Remote fallback is never automatic.

Administration > AI Platform manages providers, models, MCP servers, network approvals, and AI audit records. Knowledge & AI > AI Chat & MCP provides the dedicated chat interface.
