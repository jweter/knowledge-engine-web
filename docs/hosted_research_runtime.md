# Hosted Research Runtime

**Status:** deployment-ready operator-gated path  
**Purpose:** turn the existing Render alpha from retrieval-only into the complete, durable Research path required by Research Report v1.

## Why this exists

The application-side Research pipeline is already implemented. The remaining hosted boundary is infrastructure: the Web service needs a real persistent mount and a reachable inference service. The default `render.yaml` intentionally remains retrieval-only because automatically attaching disks or creating a model service changes the operator's recurring Render cost.

`render.research.yaml` is the explicit full-runtime Blueprint. Apply it only after the operator approves the additional paid infrastructure.

## Architecture

```text
Browser
  |
  v
knowledge-engine-web-alpha (public Web service)
  |-- /var/data persistent disk
  |     |-- Core writable research workspace
  |     |-- Evidence Records
  |     |-- Research Sessions
  |     |-- acquired papers
  |     `-- discovery ledger
  |
  `-- Render private network --> knowledge-engine-ollama
                                  |-- qwen2.5:1.5b
                                  `-- /var/data model disk
```

The model service is a Render **private service**. It has no public HTTP endpoint. `render.research.yaml` injects only its private `host:port` into the Web service. `scripts/start-alpha.sh` converts that value to the `http://host:port` URL expected by `OllamaLLM`.

## Deliberate resource choice

The private inference service uses the `1c-2g` plan and `qwen2.5:1.5b` because that model has already been exercised in the Knowledge Engine AI CPU verification work. The Web service remains on the existing starter compute tier and keeps inference isolated so model RAM/CPU cannot starve FastAPI/Core.

The Web disk starts at 1 GB and the model disk at 2 GB. Render disks can be enlarged later but cannot be shrunk, so the initial sizes are intentionally conservative.

## Activation procedure

1. Confirm the operator accepts the additional recurring Render cost for the two persistent disks and the private `1c-2g` inference service.
2. In Render, sync a Blueprint using `render.research.yaml` as the Blueprint path.
3. Preserve the existing `KE_WEB_ALPHA_USERNAME` and `KE_WEB_ALPHA_PASSWORD` secret values. Render does not retroactively prompt for new `sync: false` values on an existing Blueprint.
4. Wait for both services to deploy. The Ollama service starts immediately, then downloads `qwen2.5:1.5b` into its persistent model disk on the first run only.
5. Verify the Web service has `/var/data` mounted and that startup logs show the Core Research workspace bootstrap succeeded.
6. Verify the private model service completed `ollama pull qwen2.5:1.5b` and remains running.
7. Open `/ask` and submit a normal question. Do not use `quick=1`; Research should be the default when capability is complete.

## Product Reality acceptance

Infrastructure is not considered complete merely because both services show "Live". The following must be observed through the deployed application:

- ordinary Ask enters a durable Research session rather than retrieval-only fallback;
- the initial indexed result remains visible while Research continues asynchronously;
- session polling survives normal request boundaries and uses the persistent session database;
- provider/degradation state remains visible;
- newly acquired evidence is grounded and promoted before it can affect synthesis;
- the deterministic Research ISA / release gates remain authoritative;
- the final answer exposes resolved Evidence Record/source-detail navigation;
- unsupported claims, hidden counter-evidence, or missing direct evidence fail acceptance rather than being cosmetically hidden.

### Definitive acceptance case

Run `jweter/knowledge-engine-ai#79` (Monster Energy / approximately one-year blood-pressure question) through the normal deployed Ask form. Record:

- session ID;
- time to first grounded information;
- time to final report;
- acquisition/extraction funnel;
- provider coverage/degradation;
- promoted Evidence Record IDs;
- final ResearchState;
- every structured conclusion row and certainty;
- explicit missing approximately-one-year direct evidence, if still absent;
- counter/null evidence;
- resolved citations and evidence-detail navigation.

Research Report v1 is not complete until that deployed case passes the documented acceptance contract.

## Rollback

The code changes are additive. If hosted inference is unhealthy, keep the existing default `render.yaml` deployment or remove the private-model wiring. The application's established fail-closed behavior leaves deterministic retrieval available rather than presenting an unverified narrative.
