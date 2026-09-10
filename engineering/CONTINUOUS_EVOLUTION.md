# Continuous Engineering Evolution

This repository participates in the portfolio engineering-learning contract defined by `jweter/project-orchestrator/DoWork.txt`. This file supplements, and never replaces, this repository's own roadmap, architecture, policy, CI, security, provenance/licensing, and Product Reality authority.

## Every engineering run

- Inspect open/recent GitHub issues as an active work queue alongside PRs, CI, branches, milestones, roadmap, architecture, and control-plane evidence.
- Prioritize work using the portfolio P0-P6 rules. Finish or repair existing work before competing work in the same dependency lane.
- Apply the learning loop: **OBSERVE -> DIAGNOSE -> FIX -> VERIFY -> RECORD -> PREVENT -> REUSE -> IMPROVE**.
- For significant, recurring, cross-platform, or orchestration-revealing failures, update the repository's authoritative regression/error ledger when one exists. Capture the problem, first meaningful root cause, bounded fix, verification evidence, regression protection, residual risk, and prevention rule.
- Before changing an area with prior failure memory, inspect and apply the relevant prevention rules.
- Add automated regression protection when practical. Never weaken production validation merely to make a partial test fixture pass.
- Learn from verified successful patterns as well as failures and reuse them when repository authority permits.
- Never invent lessons, test results, Product Reality, metrics, or progress. If there is no genuinely new lesson in a run, reuse prior learning and report that fact.
- A preventable diagnosed failure class should not repeatedly consume scheduled runs. Automate prevention when safe, or document why it cannot safely be automated.

## Learned prevention rule — exact-head verification invalidation

### Problem
PR #141 received a correctness/privacy repair after its original exact-head preflight had already passed. The repaired head then reached fresh PR CI with a Ruff `I001` import-order failure in `tests/test_mobile_product_reality.py`.

### Root cause
The earlier GREEN preflight applied only to the earlier commit. Any subsequent repair commit changed the exact head and invalidated that verification evidence. The repaired head was therefore not entitled to inherit the previous preflight state. Formatting also proved insufficient as a proxy for lint: `ruff format --check` passed while `ruff check` correctly failed.

### Bounded fix
- Correct the lint failure without weakening production validation or test intent.
- Reset the repaired branch to `PREFLIGHT_UNVERIFIED` after every head-changing repair.
- Require a fresh full exact-head preflight before treating a repaired branch as promotion-ready.

### Verification
The corrective head must pass the repository's complete canonical preflight and then fresh independent PR CI. Prior GREEN evidence from an older SHA is not valid verification for the new head.

### Regression protection
- Treat any branch-head mutation after preflight as automatic invalidation of `PREFLIGHT_GREEN`.
- Run both repository formatting and lint checks on modified Python/test files; formatting success must never imply lint success.
- Keep PR verification metadata SHA-specific and mark it stale when the head changes.

### Residual risk
GitHub or orchestration surfaces may display historical successful checks from older heads. Promotion logic must bind verification to the current exact SHA rather than the branch name or PR number alone.

### Prevention rule
**Every head-changing repair invalidates prior preflight evidence. Re-run the full canonical preflight on the new exact head before promotion, and never infer lint success from formatter success.**

## Evolution objective

Improve product capability, engineering capability, autonomous reliability, and prevention effectiveness together. Target **Preventable Repeat Failure Rate = 0**. Shipping more code is not success if avoidable failures continue recurring.

## Reporting

When evidence exists, report: new failure classes, root causes established, regression protections added, lessons recorded, prior lessons reused, preventable repeat failures, and control-plane improvements. Use UNKNOWN rather than fabricated evidence.
