from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}, found {count}: {old[:80]!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: str, start_marker: str, end_marker: str, replacement: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    file_path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


# Configuration: keep local/test behavior synchronous unless explicitly enabled;
# Render opts into the asynchronous path below.
replace_once(
    "knowledge_engine_web/config.py",
    "    ai_rate_limit_window_seconds: float = Field(default=600.0, gt=0)\n"
    "    # GQR-4/GQR-5: Research mode may acquire accessible full text before\n",
    "    ai_rate_limit_window_seconds: float = Field(default=600.0, gt=0)\n"
    "    # WEB-GQR-4: hosted Research mode can return a durable session identity\n"
    "    # immediately and move the bounded AI run off the request/response cycle.\n"
    "    # Default false preserves the existing synchronous local/test seam; Render\n"
    "    # opts in explicitly once persistent session storage is configured.\n"
    "    async_research_enabled: bool = False\n"
    "    # GQR-4/GQR-5: Research mode may acquire accessible full text before\n",
)

replace_once(
    "render.yaml",
    "      - key: KE_WEB_AI_RATE_LIMIT_WINDOW_SECONDS\n"
    "        value: \"600\"\n"
    "      # WEB-FRD-1: process-local safety defaults for the separate, opt-in\n",
    "      - key: KE_WEB_AI_RATE_LIMIT_WINDOW_SECONDS\n"
    "        value: \"600\"\n"
    "      # WEB-GQR-4: return a durable session immediately, run Research Copilot\n"
    "      # in the process-local bounded worker, and let the Ask page poll progress.\n"
    "      - key: KE_WEB_ASYNC_RESEARCH_ENABLED\n"
    "        value: \"true\"\n"
    "      # WEB-FRD-1: process-local safety defaults for the separate, opt-in\n",
)

# Main application imports.
replace_once(
    "knowledge_engine_web/main.py",
    "from knowledge_engine_web.research_question import derive_research_question_id\n"
    "from knowledge_engine_web.research_session_status import read_session_status\n",
    "from knowledge_engine_web.research_jobs import (\n"
    "    is_research_job_active,\n"
    "    read_research_job,\n"
    "    submit_research_job,\n"
    ")\n"
    "from knowledge_engine_web.research_question import derive_research_question_id\n"
    "from knowledge_engine_web.research_session_status import read_session_status\n",
)

replace_once(
    "knowledge_engine_web/main.py",
    'def ask(request: Request, q: str = "", synthesize: bool = False) -> HTMLResponse:\n',
    'def ask(\n    request: Request, q: str = "", synthesize: bool = False, session_id: str = ""\n) -> HTMLResponse:\n',
)

replace_once(
    "knowledge_engine_web/main.py",
    "    synthesis_available = ai_capability.available\n"
    "    question = q.strip()\n",
    "    synthesis_available = ai_capability.available\n"
    "    async_research_enabled = settings.async_research_enabled\n"
    "    question = q.strip()\n",
)

replace_once(
    "knowledge_engine_web/main.py",
    '                "citation_entries": [],\n'
    "            },\n"
    "        )\n",
    '                "citation_entries": [],\n'
    '                "async_research_enabled": async_research_enabled,\n'
    '                "research_job_session_id": None,\n'
    '                "research_job": None,\n'
    "            },\n"
    "        )\n",
)

old_execution = '''    synthesize_requested = synthesize and synthesis_available
    synthesis_unavailable_notice = (
        "Research Copilot is unavailable on this deployment. Retrieval results are shown below."
        if synthesize and not synthesis_available
        else None
    )
    copilot_result = None
    copilot_error: str | None = None
    if synthesize_requested:
        try:
            client_key = request.client.host if request.client is not None else "unknown"
            # Generated before the run starts (rather than left to
            # run_research_question's internal UUID fallback) so this
            # identity is already known ahead of a future background-task
            # slice of WEB-GQR-4, which needs to hand a session id back to
            # the visitor before the run itself completes.
            session_id = str(uuid.uuid4())
            copilot_result = run_guarded_ai_orchestration(
                settings,
                question,
                client_key=client_key,
                session_id=session_id,
            )
            if result_reached_execution_limit(copilot_result):
                copilot_error = (
                    "Research Copilot reached its execution time limit. The durable session "
                    "records the incomplete workflow; deterministic retrieval results are "
                    "still shown below."
                )
        except AIAdmissionError as exc:
            copilot_error = exc.visitor_message
        except AIOrchestrationError as exc:
            copilot_error = str(exc)
'''
new_execution = '''    synthesize_requested = synthesize and synthesis_available
    synthesis_unavailable_notice = (
        "Research Copilot is unavailable on this deployment. Retrieval results are shown below."
        if synthesize and not synthesis_available
        else None
    )
    copilot_result = None
    copilot_error: str | None = None
    research_job_session_id = session_id.strip() or None
    research_job = None

    if synthesize_requested and async_research_enabled:
        if research_job_session_id is not None:
            research_job = read_research_job(settings.session_db_path, research_job_session_id)
            if research_job is not None and research_job.question != question:
                copilot_error = (
                    "That research session belongs to a different question. Start a new Research run."
                )
                research_job_session_id = None
                research_job = None
        else:
            client_key = request.client.host if request.client is not None else "unknown"
            research_job_session_id = str(uuid.uuid4())
            try:
                research_job = submit_research_job(
                    settings,
                    question=question,
                    client_key=client_key,
                    session_id=research_job_session_id,
                    research_question_id=derive_research_question_id(question),
                )
            except RuntimeError:
                research_job_session_id = None
                copilot_error = (
                    "Research mode could not start its background worker. Retrieval results are "
                    "still shown below."
                )
    elif synthesize_requested:
        try:
            client_key = request.client.host if request.client is not None else "unknown"
            synchronous_session_id = str(uuid.uuid4())
            copilot_result = run_guarded_ai_orchestration(
                settings,
                question,
                client_key=client_key,
                session_id=synchronous_session_id,
            )
            if result_reached_execution_limit(copilot_result):
                copilot_error = (
                    "Research Copilot reached its execution time limit. The durable session "
                    "records the incomplete workflow; deterministic retrieval results are "
                    "still shown below."
                )
        except AIAdmissionError as exc:
            copilot_error = exc.visitor_message
        except AIOrchestrationError as exc:
            copilot_error = str(exc)
'''
replace_once("knowledge_engine_web/main.py", old_execution, new_execution)

replace_once(
    "knowledge_engine_web/main.py",
    '            "citation_entries": citation_entries,\n'
    "        },\n"
    "    )\n\n\n@app.get(\"/ask/session/{session_id}\")\n",
    '            "citation_entries": citation_entries,\n'
    '            "async_research_enabled": async_research_enabled,\n'
    '            "research_job_session_id": research_job_session_id,\n'
    '            "research_job": research_job,\n'
    "        },\n"
    "    )\n\n\n@app.get(\"/ask/session/{session_id}\")\n",
)

new_status_route = '''@app.get("/ask/session/{session_id}")
def ask_session_status(session_id: str) -> Response:
    """Poll durable Research Copilot progress and the Web job presentation result.

    AI's ``research_sessions`` / ``research_events`` remain the workflow source
    of truth. WEB-GQR-4 adds a small Web job projection in the same persistent
    SQLite file so a session can be queued before AI creates its first row and a
    verified final presentation payload can survive the request that launched it.
    No provider candidate is promoted to evidence by this endpoint.
    """

    settings = Settings()
    job = read_research_job(settings.session_db_path, session_id)
    view = read_session_status(settings.session_db_path, session_id)
    if job is None and view is None:
        raise HTTPException(status_code=404, detail="No research session with that ID.")

    if job is not None:
        interrupted = not job.terminal and not is_research_job_active(session_id)
        visitor_error = job.visitor_error
        if interrupted and visitor_error is None:
            visitor_error = (
                "This in-flight research worker was interrupted by a process restart. "
                "Its durable session trace remains available; start a new Research run to continue."
            )
        payload = {
            "session_id": job.session_id,
            "research_question_id": job.research_question_id,
            "question": job.question,
            "job_status": job.status,
            "status": view.status if view is not None else job.status,
            "last_completed_stage": view.last_completed_stage if view is not None else None,
            "latest_workflow_node": view.latest_workflow_node if view is not None else None,
            "event_count": view.event_count if view is not None else 0,
            "terminal": job.terminal,
            "interrupted": interrupted,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "visitor_error": visitor_error,
            "result": job.result,
        }
        return Response(content=json.dumps(payload, indent=2) + "\n", media_type="application/json")

    assert view is not None
    payload = {
        "session_id": view.session_id,
        "question": view.question,
        "status": view.status,
        "last_completed_stage": view.last_completed_stage,
        "terminal": view.terminal,
        "created_at": view.created_at,
        "updated_at": view.updated_at,
        "event_count": view.event_count,
        "latest_workflow_node": view.latest_workflow_node,
    }
    return Response(content=json.dumps(payload, indent=2) + "\n", media_type="application/json")
'''
replace_between(
    "knowledge_engine_web/main.py",
    '@app.get("/ask/session/{session_id}")',
    '\n\n@app.get("/discover", response_class=HTMLResponse)',
    new_status_route,
)

# Ask template: an indexed miss is no longer worded as the final answer while a
# bounded async research session is active.
replace_once(
    "knowledge_engine_web/templates/ask.html",
    '''  {% else %}
  <p>I could not find evidence in the indexed corpus that directly answers &ldquo;{{ question }}&rdquo;.</p>
  <p class="disclaimer">
    Papers that only share the broad topic are not treated as answers. They are labelled
    background below.
  </p>
  {% endif %}
</section>

{% if synthesize_requested %}
''',
    '''  {% else %}
  {% if research_job_session_id %}
  <p>Indexed evidence is thin; Research mode is continuing the bounded literature search for this question.</p>
  <p class="disclaimer">
    An indexed-corpus miss is not the final scientific conclusion. Only validated Evidence Records
    can enter the researched answer, and the final result will update below when verification closes.
  </p>
  {% else %}
  <p>I could not find evidence in the indexed corpus that directly answers &ldquo;{{ question }}&rdquo;.</p>
  <p class="disclaimer">
    Papers that only share the broad topic are not treated as answers. They are labelled
    background below.
  </p>
  {% endif %}
  {% endif %}
</section>

{% if research_job_session_id %}
<section class="ask-result-card ask-synthesis" id="async-research-session" data-session-id="{{ research_job_session_id }}">
  <p class="trust-label computed">Research session running</p>
  <h3>Research Copilot</h3>
  <p class="disclaimer">
    This page returned without waiting for the full research loop. It is polling the durable session
    while indexed retrieval, scholarly discovery, acquisition, grounded extraction, re-retrieval,
    synthesis, and verification proceed under the configured budgets.
  </p>
  <p><strong>Session:</strong> <code>{{ research_job_session_id }}</code></p>
  <p id="async-research-progress" role="status" aria-live="polite">Starting bounded research...</p>
  <p class="empty-state" id="async-research-error" hidden></p>
  <div id="async-research-result" hidden>
    <p class="trust-label computed">Verified research result</p>
    <h4>Researched answer</h4>
    <p id="async-research-narrative"></p>
    <dl>
      <dt>Research state</dt><dd id="async-research-state"></dd>
      <dt>Evidence used</dt><dd id="async-research-evidence-counts"></dd>
      <dt>Provider coverage</dt><dd id="async-research-provider-coverage"></dd>
      <dt>Measured research latency</dt><dd id="async-research-latency"></dd>
    </dl>
    <div id="async-research-limitations-wrap" hidden>
      <h4>Limitations</h4>
      <ul id="async-research-limitations"></ul>
    </div>
    <div id="async-research-citations-wrap" hidden>
      <h4>Resolved citations</h4>
      <ul id="async-research-citations"></ul>
    </div>
  </div>
</section>
{% endif %}

{% if synthesize_requested and not research_job_session_id %}
''',
)

# Replace the small submit-only script with polling + safe DOM rendering. No raw
# result string is inserted with innerHTML.
ask_path = Path("knowledge_engine_web/templates/ask.html")
ask_text = ask_path.read_text(encoding="utf-8")
script_start = ask_text.rindex("<script>")
script_end = ask_text.index("</script>", script_start) + len("</script>")
new_script = r'''<script>
  (() => {
    const form = document.getElementById("ask-form");
    const submit = document.getElementById("ask-submit");
    const status = document.getElementById("ask-running-status");
    if (form && submit && status) {
      form.addEventListener("submit", () => {
        const copilot = form.querySelector('input[name="synthesize"]:checked');
        if (!copilot) return;
        submit.disabled = true;
        submit.setAttribute("aria-busy", "true");
        submit.textContent = "Working";
        status.hidden = false;
      });
    }

    const session = document.getElementById("async-research-session");
    if (!session) return;
    const sessionId = session.dataset.sessionId;
    if (!sessionId) return;

    const currentUrl = new URL(window.location.href);
    if (!currentUrl.searchParams.get("session_id")) {
      currentUrl.searchParams.set("session_id", sessionId);
      window.history.replaceState({}, "", currentUrl);
    }

    const progressNode = document.getElementById("async-research-progress");
    const errorNode = document.getElementById("async-research-error");
    const resultNode = document.getElementById("async-research-result");
    const narrativeNode = document.getElementById("async-research-narrative");
    const stateNode = document.getElementById("async-research-state");
    const evidenceNode = document.getElementById("async-research-evidence-counts");
    const providerNode = document.getElementById("async-research-provider-coverage");
    const latencyNode = document.getElementById("async-research-latency");
    const limitationsWrap = document.getElementById("async-research-limitations-wrap");
    const limitationsNode = document.getElementById("async-research-limitations");
    const citationsWrap = document.getElementById("async-research-citations-wrap");
    const citationsNode = document.getElementById("async-research-citations");

    const milliseconds = (value) => {
      if (value === null || value === undefined) return "not recorded";
      return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`;
    };

    const renderList = (wrap, list, values) => {
      if (!wrap || !list || !values || values.length === 0) return;
      list.replaceChildren();
      values.forEach((value) => {
        const item = document.createElement("li");
        item.textContent = String(value);
        list.appendChild(item);
      });
      wrap.hidden = false;
    };

    const renderCitations = (citations) => {
      if (!citationsWrap || !citationsNode || !citations || citations.length === 0) return;
      citationsNode.replaceChildren();
      citations.forEach((citation) => {
        const item = document.createElement("li");
        const evidenceId = citation.evidence_record_id || "evidence record";
        const local = document.createElement("a");
        local.href = `/claims/${encodeURIComponent(evidenceId)}`;
        local.textContent = evidenceId;
        item.appendChild(local);
        if (citation.paper_citation) {
          item.appendChild(document.createTextNode(` — ${citation.paper_citation}`));
        }
        if (citation.paper_source_url) {
          try {
            const sourceUrl = new URL(citation.paper_source_url);
            if (sourceUrl.protocol === "http:" || sourceUrl.protocol === "https:") {
              const source = document.createElement("a");
              source.href = sourceUrl.href;
              source.textContent = " source";
              source.rel = "noopener noreferrer";
              item.appendChild(source);
            }
          } catch (_error) {
            // Invalid provider URL stays unlinked rather than becoming markup.
          }
        }
        citationsNode.appendChild(item);
      });
      citationsWrap.hidden = false;
    };

    const renderResult = (result) => {
      if (!resultNode || !result) return;
      const progress = result.progress || {};
      const funnel = result.conversion_funnel || {};
      if (narrativeNode) {
        narrativeNode.textContent = result.narrative_releaseable && result.narrative
          ? result.narrative
          : "Research completed, but deterministic verification or the Research ISA close gate did not permit a narrative to be released.";
      }
      if (stateNode) stateNode.textContent = result.research_state || "unknown";
      if (evidenceNode) {
        const indexed = (progress.indexed_evidence_record_ids || []).length;
        const acquired = (progress.newly_acquired_evidence_record_ids || []).length;
        evidenceNode.textContent = `${indexed} indexed before the run; ${acquired} newly grounded and promoted during the run`;
      }
      if (providerNode) {
        const providers = progress.provider_statuses || [];
        const attempted = providers.filter((provider) => provider.attempted).length;
        const degraded = providers.filter((provider) => provider.outcome && provider.outcome !== "success").length;
        const completeness = progress.provider_coverage_completeness || "not recorded";
        providerNode.textContent = `${attempted} provider(s) attempted; ${degraded} degraded; coverage ${completeness}`;
      }
      if (latencyNode) {
        latencyNode.textContent = `first grounded information: ${milliseconds(funnel.time_to_first_grounded_information_ms)}; final report: ${milliseconds(funnel.time_to_final_report_ms)}`;
      }
      renderList(limitationsWrap, limitationsNode, progress.limitations || []);
      renderCitations(progress.citations || []);
      resultNode.hidden = false;
    };

    let delayMs = 1000;
    const poll = async () => {
      try {
        const response = await fetch(`/ask/session/${encodeURIComponent(sessionId)}`, {
          headers: { Accept: "application/json" },
          cache: "no-store",
        });
        if (!response.ok) throw new Error(`status ${response.status}`);
        const data = await response.json();
        const created = Date.parse(data.created_at);
        const elapsed = Number.isNaN(created) ? null : Math.max(0, Date.now() - created);
        if (progressNode) {
          if (data.job_status === "queued") {
            progressNode.textContent = `Queued for bounded research${elapsed === null ? "" : ` — ${milliseconds(elapsed)} elapsed`}.`;
          } else if (data.last_completed_stage) {
            progressNode.textContent = `Last completed: ${data.last_completed_stage}. Research continues${elapsed === null ? "" : ` — ${milliseconds(elapsed)} elapsed`}.`;
          } else {
            progressNode.textContent = `Research session is running${elapsed === null ? "" : ` — ${milliseconds(elapsed)} elapsed`}.`;
          }
        }
        if (data.interrupted) {
          if (errorNode) {
            errorNode.textContent = data.visitor_error || "The research worker was interrupted.";
            errorNode.hidden = false;
          }
          return;
        }
        if (data.terminal) {
          if (data.job_status === "completed" && data.result) {
            if (progressNode) progressNode.textContent = "Bounded research completed.";
            renderResult(data.result);
          } else if (errorNode) {
            errorNode.textContent = data.visitor_error || "Research mode did not complete this session.";
            errorNode.hidden = false;
          }
          return;
        }
        delayMs = Math.min(5000, Math.round(delayMs * 1.35));
        window.setTimeout(poll, delayMs);
      } catch (_error) {
        if (progressNode) {
          progressNode.textContent = "The session is still pending; the progress endpoint is temporarily unavailable. Retrying...";
        }
        delayMs = Math.min(5000, Math.round(delayMs * 1.5));
        window.setTimeout(poll, delayMs);
      }
    };
    window.setTimeout(poll, 250);
  })();
</script>'''
ask_path.write_text(ask_text[:script_start] + new_script + ask_text[script_end:], encoding="utf-8")

# Documentation records exactly what this slice does and does not promise.
docs_path = Path("docs/general_question_research_loop_v1.md")
docs = docs_path.read_text(encoding="utf-8")
marker = "### WEB-GQR-5 - Failure drills\n"
if marker not in docs:
    raise RuntimeError("WEB-GQR-5 marker missing")
addition = '''**Second slice — asynchronous Render execution and polling:** Web now has a durable
`web_research_jobs` projection in the same configured persistent SQLite file. With
`KE_WEB_ASYNC_RESEARCH_ENABLED=true`, `/ask?synthesize=1` allocates the caller-owned
session ID, persists a queued job, submits the existing bounded Research Copilot call to
a single process-local worker, and returns the Ask page immediately. The page preserves
the session ID in its URL, polls `GET /ask/session/{session_id}`, renders the latest
*completed* durable AI stage without inventing a percent-complete estimate, and replaces
the running state with the verified presentation payload when the job closes. The final
payload includes AI's BT-6 progress report and BT-2 conversion funnel, so indexed-vs-new
evidence, provider degradation, citations/limitations, time-to-first-grounded-information,
and time-to-final-report are visible without scraping narrative prose.

This is intentionally **not** a distributed/resumable workflow engine. The research
session/events and completed Web presentation survive refresh and a Render redeploy when
`/var/data` is provisioned. A process restart during the Python call cannot resume that
in-flight call; the poll endpoint reports the interruption instead of silently restarting
or pretending the work completed. True execution resume remains a later AI durable-workflow
engine milestone.

#### Definitive deployment acceptance: Monster #79

After this slice reaches Render, the first full acceptance run is AI golden research case
`monster-energy-bp-one-year` (issue #79): two 16-fl-oz Monster drinks/day for approximately
one year, keeping Zero Ultra and Original distinct and preserving acute-vs-chronic BP,
incident-hypertension, measurement-artifact, direct-vs-indirect evidence, counter-evidence,
and missing-long-term-evidence boundaries. Record the returned session ID, BT-2 funnel,
time to first grounded information, time to final report, provider degradation, promoted
Evidence Records, final research state, and whether every released factual claim resolves
to a source. The acceptance run must fail honestly rather than manufacture a preferred
scientific conclusion.

'''
docs_path.write_text(docs.replace(marker, addition + marker, 1), encoding="utf-8")
