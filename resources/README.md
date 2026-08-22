# NatureAI Next Local AI Resource Kit

NatureAI Next does not ship third-party model weights or taxonomy data. Internet access is permitted only when the user explicitly obtains those resources. This kit converts local files into the signed offline formats accepted by **Manage local AI resources…**.

## 1. Generate a local signing identity

```powershell
natureai-next-resources key-generate `
  --key-id natureai-local `
  --private-key D:\NatureAI-Models\signing\natureai-local-private.pem `
  --trusted-keys D:\NatureAI-Models\signing\natureai-local-trusted.json
```

Keep the private key private and backed up. The trusted-key JSON may be selected in the NatureAI resource manager.

## 2. Build a BioCLIP/OpenCLIP model package

Obtain the upstream checkpoint separately and verify its license and checksum. Copy `templates/model-package.example.json` beside the checkpoint, update its metadata, then run:

```powershell
natureai-next-resources model-build `
  --config D:\NatureAI-Models\build\model-package.json `
  --private-key D:\NatureAI-Models\signing\natureai-local-private.pem `
  --output D:\NatureAI-Models\packages\bioclip-model.zip
```

Validate before installation:

```powershell
natureai-next-resources model-verify D:\NatureAI-Models\packages\bioclip-model.zip `
  --trusted-keys D:\NatureAI-Models\signing\natureai-local-trusted.json
```

## 3. Build a taxonomy package

Prepare `taxa.jsonl`, `names.jsonl`, and optionally `regions.jsonl` in one directory. Copy and edit `templates/taxonomy-package.example.json`, then run `taxonomy-build` and `taxonomy-verify`.

## 4. Validate a prompt set

Copy and edit `templates/prompt-set.example.json`. Every taxon prompt must reference a public taxon ID installed from the taxonomy package.

```powershell
natureai-next-resources prompt-verify D:\NatureAI-Models\prompts\prompts.json `
  --model-family bioclip
```

Install model, taxonomy, and prompt resources through **AI Review → Manage local AI resources…**, then build taxonomy embeddings.

## Reproducible workspace with absolute paths

After installation, open a new PowerShell window and run:

```powershell
natureai-next-resources workspace-init --root D:\NatureAI-Models --key-id natureai-local
```

The command creates the full directory layout, absolute checkpoint path in `build\model-package.json`, taxonomy source placeholders, a prompt manifest, and `BUILD_COMMANDS.ps1`. Place the licensed upstream checkpoint at the exact path reported by the command before building the signed package.
