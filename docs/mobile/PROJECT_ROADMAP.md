# Knowledge Engine Pocket — New Mobile Project Charter

**Planning status:** proposed separate iOS product track; **not** a current executable iOS app, installed service, or owner runtime-mode change. 2026-11-01.

**Parent project:** [Knowledge Engine family (Core + AI + Web)](https://github.com/jweter/knowledge-engine-web)  
**Product form:** Unified offline scientific reading, evidence library and grounded research app  
**Project ID:** `knowledge_engine_pocket`

## Vision and product promise

Build one private, on-device scientific research application that imports and organizes user-selected PDFs/evidence packages, searches a bounded local library, extracts and displays verifiable citations, and composes locally grounded notes/reports. Online discovery and existing Core/AI/Web capabilities become optional integrations, not required infrastructure.

## Current verified foundation

Core is Python-based scientific source/evidence storage with provenance and recent on-demand online-evidence work; AI is the research orchestration layer; Web has question-first pages and `mobile_product_reality.py` / mobile review store. Current default AI/Web paths retain local-corpus/Ollama dependencies, so on-device native independence is a new mobile implementation, not a direct copy of server code.

## First real user journey

In airplane mode, import two scientific PDFs or a verified evidence bundle from Files, generate/inspect text and source metadata locally, search for a topic, select supported excerpts, annotate limitations and write a saved evidence-backed comparison with tappable citations to exact local document positions.

## Non-negotiable standalone contract

- PDFKit reading, Files import/export, Vision on-device OCR for scanned pages, local source hashing, local evidence/notes, and SQLite FTS5 search.
- Each citation binds to a local source ID, digest, page/offset/span and actual visible text; manual note claims remain distinguishable from extracted evidence.
- Offline grounded summaries may use deterministic templates first; optional on-device small model only after benchmarks and no ungrounded fabrication or hidden source invention.
- Fresh online research is necessarily unavailable in airplane mode; show 'offline corpus only' prominently and allow later user-initiated retrieval.

## Optional connected expansion (not a dependency)

User-initiated online research retrieves new public sources through existing Core/Web contracts or future direct adapters; optional sync for library and reports. Never require a persistent Core Python server or Ollama. Offline locally saved papers and reports stay usable after disconnect.

## Out of scope and honest feasibility boundary

Genuine fresh literature research needs network for retrieval, but all saved/imported source reading and evidence synthesis can be made fully standalone. A mobile app does not replace the three maintained parent repos.

## Portfolio operating principles

- Phone-first: app launches and performs its declared MVP value in airplane mode without Azathoth, GitHub, a hosted API, or a paid service.
- Native-first for the long run; a PWA or companion prototype may validate UX sooner, but may not be represented as proof of fully native offline functionality.
- One source of product truth: share formats, algorithms and fixtures with parent project; never fork the entire Python/Windows backend or invent duplicate business rules.
- Optional sync must be explicit, authenticated, revocable and resilient to disconnection; an offline session must never trigger an implicit network request.
- Protect user data: use iOS sandbox, Files integration, file protection/Keychain for secrets; avoid collecting unnecessary user content and telemetry.
- Keep parent project quality policies: narrow branches, exact-head tests, licensing/provenance checks, review and product reality. Do not install or alter the running Iron God release.
- Measure device performance, memory, thermals and battery on physical supported iPhones; record actual evidence before making capability or compatibility claims.
- Maintain accessibility (VoiceOver, Dynamic Type where applicable, contrast, touch targets), cancel/resume behavior and storage bounds.
- No Apple membership purchase, Mac rental, new paid service, signing certificate or public App Store distribution without separate explicit owner decision.

## Build environment and cost constraints

Native iOS signing, on-device testing and App Store submission normally require macOS/Xcode infrastructure; the Windows laptop can remain the source-development and test workstation. Start with portable C++/Swift contract fixtures and SwiftUI design prototypes where a Mac runner/device is not yet available. Personal device development can start without paid Apple Developer Program membership, subject to Apple's provisioning limits; App Store/TestFlight distribution requires program enrollment.

Default cost target $0 before owner-approved developer membership, build-machine access or cloud usage. Keep optional model downloads, paid APIs, hosted inference and other recurring costs opt-in. No automatic spending.

## Parent-code and platform references

- https://github.com/jweter/knowledge-engine-core
- https://github.com/jweter/knowledge-engine-ai
- https://github.com/jweter/knowledge-engine-web/blob/main/knowledge_engine_web/mobile_product_reality.py
- https://developer.apple.com/documentation/vision/recognizing-text-in-images


---

# Knowledge Engine Pocket — Phased iPhone Roadmap

**Status:** PLANNED. Phases are evidence gates, **not calendar commitments**. Parent projects retain authority over their existing implementation and product quality.

## Release strategy

Start by proving a no-server/no-laptop local user journey. Give native/local capabilities their own implementation and acceptance tests. Add external integrations only after the standalone core works. For every phase: maintain a narrow branch, exact-head tests, real device evidence and explicit limitations; do not call draft prototypes complete.

## P0 — Cross-repository mobile evidence contract

**Deliverables**

- Audit Core evidence bundle schema, provenance offsets/cache retention, Web report metadata and AI structured citations.
- Define versioned, privacy-safe mobile import/export package with PDF hashes, offsets, source states and citations.
- Build real test fixtures including unavailable, contradictory and failed sources; avoid silent 'consensus' assertions.

**Exit gate:** All three parent repos can validate a fixture; imported evidence never loses source identity, uncertainty or unsupported-source errors.

## P1 — True offline research library

**Deliverables**

- Create SwiftUI PDF reader, Files import, provenance-hashed immutable local source registry and local delete/export.
- Implement SQLite FTS5 search and result-to-original-page navigation; Vision OCR only on supported files, with visible confidence/limitations.
- Bound cache/storage; add database migration, airplane mode and reboot tests.

**Exit gate:** Import, search, cite and reopen two local PDFs entirely offline, with no server, network or pre-ingested database required.

## P2 — Evidence notebook and offline report

**Deliverables**

- Create extract/highlight/annotate workflow and structured claim/evidence/limitation builder.
- Generate a deterministic source-grounded Research Report from local selected evidence; refuse unsupported citations.
- Export a report with stable links and source manifest to Files; validate source/offset integrity after reopening.

**Exit gate:** One question yields an inspectable report citing actual locally stored passages and unresolved uncertainty without model-generated fake references.

## P3 — Optional on-device research assistant

**Deliverables**

- Benchmark one small permissively licensed local model for summarization/semantic query decomposition on target iPhone; keep retrieval deterministic.
- Add guarded prompt construction with source-bounded citations, deterministic post-validation and a model-off fallback.
- Profile battery/RAM/thermal/storage and cross-repo exact-span fidelity.

**Exit gate:** Model-enabled result is demonstrably grounded, and disabling/removing the model still leaves a complete offline research product.

## P4 — On-demand online discovery and sync

**Deliverables**

- Add explicitly triggered source discovery/retrieval when connectivity is available, with source status/error taxonomy and cache expiry.
- Import verified Core evidence bundles and optionally publish reports to existing Web experience; protect private source material.
- Test airplane-mode transitions, failed retrieval and deleted/superseded source versions.

**Exit gate:** Online enhancement does not degrade offline use, and no inaccessible source is silently cited.

## P5 — Privacy and native beta

**Deliverables**

- Test multi-PDF real workloads on physical iPhone and iPad where available; calibrate OCR/search latency, RAM and storage limits.
- Validate VoiceOver citations, Dynamic Type, import/export and security/privacy model.
- Prepare App Store privacy declarations only after determining distribution and consent.

**Exit gate:** Offline evidence chain passes genuine physical device review and no remote backend is necessary for first-use research.

## First independently actionable engineering slices

1. KEP-001: map Core/AI/Web versioned evidence and report contracts
2. KEP-002: native offline PDF + provenance-hash import spike
3. KEP-003: SQLite FTS5 page-linked search proof
4. KEP-004: citation/offset validation and offline evidence notebook
5. KEP-005: optional small-model evaluation and no-model fallback

## External blockers / decisions held for later

Genuine fresh literature research needs network for retrieval, but all saved/imported source reading and evidence synthesis can be made fully standalone. A mobile app does not replace the three maintained parent repos.

Open decisions to defer: name/icon/branding; minimum iOS version and target devices after a build smoke; distribution model and monetization; Apple signing infrastructure; optional online sync; optional on-device inference models. None block offline planning and portable-contract work.

## Change-control and roadmap hygiene

This iOS roadmap is a distinct **proposal** and does not silently expand the owner-approved desktop implementation roadmap. On approval of a phase, add narrowly bounded capability graph entries or planning issues in the appropriate development project; do not auto-enroll these proposals in the active Iron God production dispatcher, grant runtime execution rights, or compete with its owner/session control. Cross-repo dependencies must reference the specific parent schema/commit and explicit acceptance evidence. Record verified milestone outcomes, not guesses.


---

# Knowledge Engine Pocket — Architecture, Risks and Validation

## System components and reuse seams

- `Reader` (SwiftUI/PDFKit/Files), `LocalCorpus` (SQLite FTS5, immutable source hashes, bounded storage, OCR), `EvidenceSpan` (source/page/offset/provenance), `ResearchNotebook` (notes and export).
- `GroundingGuard` fail-closed citation checker: no claim of source support without matching local bytes and cited span.
- `OptionalOnDeviceAI` model provider with performance/license/version and deterministic constrained outputs; report provenance must remain inspectable.
- `CoreAIWebImportExportAdapter` versioned schemas using representative real evidence bundles and shared fixtures, not importing Python implementations wholesale.

## Offline / optional-online data flow

**Offline:** Files / mic / touch input → local validated parser → versioned local store → deterministic logic and (if proven) on-device inference → local UI / Files export. No remote call is necessary for the core workflow.

**Online enhancement:** explicit user action → permission/identity check → versioned optional adapter → external backend or online public source → source/receipt validation → local persisted result. Network failure leaves the offline product functional; remote-only operations fail visibly and never impersonate local results.

## Technical and delivery risks

- **Python portability:** Core/AI/Web Python packages should not be assumed to run natively on iOS; reuse portable formats/algorithms via Swift/C++ adapters.
- **Offline vs fresh research:** New online sources cannot be discovered without a network; offline mode searches imported/saved sources only.
- **Hallucinated citations:** Strict hash/source-span verification required for every AI-generated or deterministic report reference.
- **Storage explosion:** On-device PDF/OCR/index/model sizes need explicit quotas and user-managed cleanup.

## Cross-cutting real-device acceptance matrix

1. Fresh install + airplane mode + Azathoth completely off: app launches and completes the documented core user journey without stalls or hidden remote services.
2. Cold start, memory peak, battery/thermal behavior, model/download size and task latency measured on an actual physical device. Set release budgets from the first spike rather than inventing benchmark successes.
3. No unauthenticated inbound listening port, leaked token, bundled source secret, plaintext private sync credential or surprise upload; perform negative network test.
4. App returns a visible failure state when inputs, permissions, local model assets or Files permissions are missing. No fabricated output or false completion.
5. User can export, back up and delete locally created work without a server; app survives force quit and offline relaunch without losing completed edits.
6. Cross-platform contract/fixture tests verify imported/exported formats against the parent repository; snapshots are not treated as live or authoritative.
7. Standard automated checks, independent review, privacy/permissions declarations, App Store licensing/provenance review and actual iPhone product test must pass before external beta.

## Release evidence template

- Exact source head and build identity; Xcode/SDK/device/OS and model/runtime version if used.
- Recorded airplane-mode test with desktop/server powered off, input fixtures, expected outputs, pass/fail and timings.
- Memory/CPU/battery/thermal/storage measurements; accessible UI screen review; interruption/resume evidence.
- Data privacy/security review, license inventory, signed-build provenance, reviewer approval and open blocker list.
- Explicit distinction: proposed concept vs prototype vs device-proven vs App Store distributable.

## References

- https://github.com/jweter/knowledge-engine-core
- https://github.com/jweter/knowledge-engine-ai
- https://github.com/jweter/knowledge-engine-web/blob/main/knowledge_engine_web/mobile_product_reality.py
- https://developer.apple.com/documentation/vision/recognizing-text-in-images
