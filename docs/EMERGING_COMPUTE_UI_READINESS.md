# Emerging-Compute UI Readiness

## Purpose

Knowledge Engine Web should be able to present future quantum, quantum-inspired, simulator, QPU, photonic, neuromorphic, and other experimental-compute evidence **without turning technical novelty into an implied endorsement**.

This document coordinates with Knowledge Engine Core issue #498 and the portfolio Emerging Compute Evaluation policy in `project-orchestrator`.

No runtime quantum dependency is introduced here.

## UI principle

The interface should answer:

**What was tested, on which substrate, against what baseline, under what conditions, at what cost, with what uncertainty, and how independently was it verified?**

It should not reduce those questions to a “quantum = better” badge.

## Evidence classes the UI should preserve

When Core/AI eventually expose them, do not collapse these into one generic result:

- theoretical result;
- classical simulation;
- quantum simulator experiment;
- physical hardware run;
- hardware run with noise/error-mitigation context;
- independent reproduction;
- classical comparator.

## Future result card contract

A compute-experiment result should be able to display, when supplied by upstream contracts:

- problem/objective;
- substrate class;
- backend/device/environment identity;
- classical baseline identity;
- measurement contract;
- candidate state (`BASELINE_REQUIRED`, `GATHER_EVIDENCE`, `SIMULATE_FIRST`, `APPROVAL_REQUIRED`, `NOT_JUSTIFIED`, `FORBIDDEN`, or `ELIGIBLE_FOR_BOUNDED_EXPERIMENT`);
- problem-fit/scientific-validity status;
- shots/replicates/seeds when material;
- variance/confidence/repeatability evidence;
- queue/execution/wall-clock time where meaningful;
- financial cost;
- verification count and evidence links;
- provenance/source links;
- safety/claim limitations.

Missing material evidence must render as missing/unknown, not be silently hidden in a way that implies certainty.

## Claim language

The Web layer must distinguish:

- **bounded benchmark superiority**: candidate beat the recorded classical baseline under a particular contract;
- **general quantum advantage**: a much stronger scientific claim that a local product benchmark does not establish.

Do not render “quantum advantage,” “quantum speedup,” or equivalent language merely because an experiment state says `BENCHMARK_SUPERIORITY_VERIFIED`.

Recommended bounded language:

> Candidate outperformed the recorded classical baseline for this benchmark under the stated measurement contract.

## Comparison design

If/when this becomes a user-facing feature, the default comparison should place substrates side-by-side under the **same measurement contract**. Suggested dimensions:

| Dimension | Classical baseline | Candidate |
| --- | --- | --- |
| Correctness / solution quality | value | value |
| Runtime | value | value |
| Wall-clock/queue time | value | value |
| Variance/repeatability | value | value |
| Cost | value | value |
| Environment/backend | identity | identity |
| Independent verification | refs/count | refs/count |
| Operational complexity | level | level |

This prevents a visually impressive candidate from hiding worse cost, reproducibility, or operational burden.

## UX states

### `BASELINE_REQUIRED`

Explain that a meaningful comparison cannot be made until a verified classical baseline exists.

### `GATHER_EVIDENCE`

Show the specific missing evidence, such as environment identity, reproducibility protocol, or scientific mapping.

### `SIMULATE_FIRST`

Explain that lower-cost simulation can answer the current question before physical hardware is justified.

### `APPROVAL_REQUIRED`

Show that the candidate crosses a cost/authority boundary. Do not imply approval is a technical failure.

### `NOT_JUSTIFIED`

Explain the evidence-based reason: low problem fit, unsupported mechanism, contract mismatch, or insufficient project value.

### `FORBIDDEN`

Show the governing boundary without offering a bypass.

### `ELIGIBLE_FOR_BOUNDED_EXPERIMENT`

Make clear that eligibility means “safe to test under the contract,” not “known to be better.”

## Accessibility and anti-hype requirements

- Do not encode substrate quality using color alone.
- Keep uncertainty and missing evidence readable by assistive technology.
- Avoid animation/visual treatment that implies quantum results are inherently special or superior.
- Preserve raw evidence links and machine-readable result identity where available.
- Use the same visual hierarchy for a classical candidate that beats a quantum candidate as for the reverse.

## Activation trigger

Do not implement product UI now. Implementation becomes justified only when Core/AI expose a stable experiment/result contract and at least one real Knowledge Engine experiment needs human-readable comparison.

Until then, this document prevents future UI work from inventing semantics independently of Core/AI.
