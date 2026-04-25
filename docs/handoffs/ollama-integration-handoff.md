# Ollama Integration Handoff

**Date:** 2026-04-18
**Author:** Staff Engineer (automated)
**Status:** Complete

---

## What was done

Added Ollama as a local LLM inference service to the AgentCompany Docker Compose
stack, wired it to the agent-runtime, and updated the configuration layer so the
default model can be changed without code edits.

---

## Files changed

| File | Change |
|------|--------|
| `docker-compose.yml` | Added `ollama` service and `ollama_data` volume; added `OLLAMA_BASE_URL` env var and `ollama` health dependency to `agent-runtime` |
| `docker-compose.override.yml` | **New** — CPU-only override that strips the NVIDIA GPU reservation |
| `.env.example` | Added `OLLAMA_PORT`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_GPU_ENABLED` |
| `scripts/ollama-setup.sh` | **New** — idempotent script that waits for Ollama and pulls `gemma3` + `nomic-embed-text` |
| `services/agent-runtime/app/config.py` | Added `ollama_base_url` and `ollama_default_model` settings fields |
| `services/agent-runtime/app/engine/llm/ollama.py` | Changed default `base_url` and `model` to read from `Settings`; changed default model from `llama3.2` to `gemma3` |
| `docs/architecture/infrastructure.md` | Added Ollama to the network diagram, port table, volume table, dependency graph, and resource table; added GPU setup section |

---

## Design decisions

### Why gemma3 and not gemma4

Gemma 4 has not been released as of the implementation date.  `gemma3` is the
current latest stable release in the Gemma family and is available in the
Ollama model registry.

### Why nomic-embed-text

It is the most widely used open embedding model in the Ollama ecosystem and is
small enough (~274 MB) to pull quickly.  It can be used for vector search
without requiring an external embedding API.

### Why docker-compose.override.yml

Docker Compose's GPU device reservation syntax (`deploy.resources.reservations.devices`)
causes `docker compose up` to fail on hosts without a configured NVIDIA runtime,
even if the GPU capability is not actually used.  The override file blanks out
the `deploy` block so the stack starts on CPU-only machines without manual edits
to the main compose file.

Developers with GPUs rename or delete the override file.  This keeps the source
of truth (GPU config) in `docker-compose.yml` and the CPU fallback in a
conventional override location.

### Why OllamaAdapter reads from Settings lazily

The adapter previously hardcoded `http://localhost:11434/v1`.  Inside Docker
Compose the correct host is `ollama:11434`, not `localhost`.  Reading from
`get_settings()` at construction time (not import time) means:

- Tests can override `OLLAMA_BASE_URL` in the environment before importing the adapter.
- The value flows through the same validated pydantic-settings path as every
  other config value.
- Operators change the endpoint without touching code.

---

## How to use

### First boot

```bash
cp .env.example .env          # adjust secrets as prompted
./scripts/setup.sh            # starts all services
./scripts/ollama-setup.sh     # pulls gemma3 and nomic-embed-text
```

The setup script is idempotent — safe to re-run after container restarts.

### GPU-enabled hosts

```bash
# Remove the CPU override so the GPU reservation in docker-compose.yml takes effect
mv docker-compose.override.yml docker-compose.override.yml.cpu-backup

# Install the NVIDIA Container Toolkit on the host (one-time):
# https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

docker compose up -d
./scripts/ollama-setup.sh
```

### Changing the default model

Set `OLLAMA_MODEL` in `.env` and re-run `ollama-setup.sh` to pull the new model:

```bash
OLLAMA_MODEL=llama3.2 ./scripts/ollama-setup.sh
```

The agent-runtime reads `OLLAMA_BASE_URL` and the `ollama_default_model` setting
from the environment on startup.

### Verifying Ollama is running

```bash
curl http://localhost:11434/api/tags          # list available models
curl http://localhost:11434/api/generate \
  -d '{"model":"gemma3","prompt":"Hello","stream":false}'
```

Or exec into the container:

```bash
docker compose exec ollama ollama list
docker compose exec ollama ollama run gemma3 "Hello"
```

---

## Known limitations and follow-up work

- **Model warm-up time:** The first request to a model takes 10–30 seconds while
  Ollama loads weights into memory.  A follow-up ticket should add a readiness
  probe that pre-warms the model after `ollama-setup.sh` completes.

- **Context window:** `OllamaAdapter` defaults to `8192` tokens, which is a
  conservative floor.  `gemma3` supports 128 k context when Ollama is configured
  with `OLLAMA_NUM_CTX=131072`.  A follow-up ticket should surface this as a
  per-agent `llm_config` option.

- **Embedding pipeline:** `nomic-embed-text` is pulled but not yet wired into any
  vector search path.  A follow-up ticket should create an `OllamaEmbedAdapter`
  that calls `/api/embeddings` and integrate it with the Meilisearch or pgvector
  backend.

- **`setup.sh` does not call `ollama-setup.sh`:** The main setup script does not
  automatically pull models after `docker compose up` because model downloads
  are large and slow.  A follow-up ticket should decide whether to add an opt-in
  flag (`--pull-models`) or a separate Make target.
