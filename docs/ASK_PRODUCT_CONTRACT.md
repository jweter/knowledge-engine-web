# Ask Product Contract

`/ask` is a question-answering surface, not a paper-listing surface.

For every submitted question, the product must:

1. preserve meaningful query terms, including short scientific terms such as `IQ`;
2. retrieve evidence that addresses the submitted question rather than merely sharing a broad topic;
3. distinguish **directly relevant evidence** from **related background**;
4. present a direct response before paper details;
5. never imply that a related paper answers an outcome it did not study;
6. say clearly when the indexed evidence cannot answer the question;
7. keep source papers and stored evidence visible underneath the response for inspection;
8. automatically use the bounded Research Copilot path when it is available; retrieval-only behavior is an explicit fast-mode choice or an honest capability fallback, not the normal Ask default.

When the complete Research capability is available, submitting an ordinary `/ask?q=...` request starts Research automatically. The product may show indexed evidence immediately, but thin indexed coverage is a transition into broader research rather than an invitation for the user to discover and enable a second mode.

`quick=1` is the explicit retrieval-only user choice. The legacy `synthesize=1` and `synthesize=0` query parameters remain compatible, but the absence of either parameter means Research-first behavior.

A successful Ask result therefore follows:

`question -> relevance-qualified evidence -> direct response -> supporting sources`

not:

`question -> broad topical papers -> user must infer an answer`.

## Relevance rule

Candidate generation may remain broad for recall, but the final Ask surface must apply a directness threshold before calling a result relevant. A document that matches only the intervention/topic but not the requested outcome must not be promoted as answering the question.

## No-answer behavior

When no indexed source clears the directness threshold, Ask should respond that no direct evidence was found in the indexed corpus. Related background may still be shown separately, explicitly labeled as background rather than an answer.
