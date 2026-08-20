"""Deterministic "tracked question" identity for `/discover` (WEB-FRD-5, item 5).

`docs/roadmap/web_frd5_freshness_history_design.md` section 5 (item 5) calls
for "a product concept of 'a tracked research question' for `/discover` --
at minimum a stable, bookmarkable identifier a person's browser can return
to... which becomes the `research_question_id` passed on every run."

This module makes that identifier a pure function of the normalized query
text rather than a random value a person would have to remember to bookmark:
asking the same question again -- today, next week, from a different
browser or device -- deterministically reproduces the same
`research_question_id`, which is exactly the worked scenario
`web_frd5_freshness_history_design.md` section 1 describes ("They come back
on 2026-08-19 and ask the *same* question again"). No user account, cookie,
or client-held state is required for two runs to be recognized as "the same
tracked question."

This is deliberately a pure function with no I/O: it does not decide
whether the identifier's history is durable (that is
`discovery_orchestration.py`'s ledger-persistence concern, item 6) and does
not read or write anything itself.
"""

from __future__ import annotations

import hashlib

_PREFIX = "rq-web-"


def derive_research_question_id(query: str) -> str:
    """Return a stable, deterministic tracked-question ID for `query`.

    Normalization (case-folded, whitespace-collapsed) means trivial
    formatting differences -- extra spaces, capitalization -- do not
    fracture one question's history across multiple IDs. This is a
    presentation-layer identity only: Core's ledger treats whatever string
    it is given as an opaque tag (see
    `knowledge-engine-core`'s `docs/core_interface_contract.md`); Web owns
    deciding what counts as "the same question," per this milestone's own
    division of labor (design doc section 3).
    """

    normalized = " ".join(query.strip().casefold().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{_PREFIX}{digest[:24]}"


__all__ = ["derive_research_question_id"]
