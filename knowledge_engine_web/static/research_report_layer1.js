(() => {
  "use strict";

  const text = (value, fallback = "not available") => {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  };

  const element = (tag, className) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    return node;
  };

  const appendText = (parent, tag, value, className) => {
    const node = element(tag, className);
    node.textContent = text(value);
    parent.appendChild(node);
    return node;
  };

  const appendList = (parent, values, emptyText, className) => {
    const items = Array.isArray(values) ? values.filter((value) => value !== null && value !== undefined && value !== "") : [];
    if (items.length === 0) {
      appendText(parent, "p", emptyText, "disclaimer");
      return;
    }
    const list = element("ul", className);
    items.forEach((value) => appendText(list, "li", value));
    parent.appendChild(list);
  };

  const renderConclusionRow = (tbody, row) => {
    const tr = document.createElement("tr");
    appendText(tr, "td", row.question_dimension, "research-report-dimension");
    appendText(tr, "td", row.conclusion);

    const certaintyCell = document.createElement("td");
    const certainty = element("strong");
    certainty.textContent = text(row.certainty);
    certaintyCell.appendChild(certainty);
    if (row.certainty_rationale) {
      const details = element("details", "discovery-method-details");
      const summary = document.createElement("summary");
      summary.textContent = "Why this certainty";
      details.appendChild(summary);
      appendText(details, "p", row.certainty_rationale, "disclaimer");
      certaintyCell.appendChild(details);
    }
    tr.appendChild(certaintyCell);

    const missingCell = document.createElement("td");
    if (row.missing_direct_evidence) {
      appendText(
        missingCell,
        "span",
        row.missing_direct_evidence,
        "trust-warning is-critical research-report-missing-evidence"
      );
    } else {
      appendText(missingCell, "span", "No missing direct-evidence item reported", "disclaimer");
    }
    tr.appendChild(missingCell);
    tbody.appendChild(tr);
  };

  const renderEvidenceRelationship = (parent, row) => {
    const section = element("section", "research-report-evidence-relationship");
    appendText(section, "h5", row.question_dimension || "Unspecified question dimension");
    appendText(section, "p", `Directness: ${text(row.directness)}`, "trust-label computed");

    appendText(section, "h6", "Supporting evidence IDs");
    appendList(
      section,
      row.supporting_evidence_ids,
      "No supporting EvidenceRecord IDs were reported for this conclusion.",
      "research-report-evidence-ids supporting"
    );

    appendText(section, "h6", "Null / contradictory evidence IDs");
    appendList(
      section,
      row.contradicting_or_null_evidence_ids,
      "No null or contradictory EvidenceRecord IDs were reported for this conclusion.",
      "research-report-evidence-ids counter"
    );

    if (row.missing_direct_evidence) {
      appendText(section, "p", `Missing direct evidence: ${row.missing_direct_evidence}`, "trust-warning is-critical");
    }
    parent.appendChild(section);
  };

  const renderProviderCoverage = (parent, report) => {
    appendText(parent, "h4", "Provider coverage and degradation");
    appendText(
      parent,
      "p",
      `Coverage completeness: ${text(report.provider_coverage_completeness)}`,
      "trust-label computed"
    );

    appendText(parent, "h5", "Degraded providers");
    appendList(
      parent,
      report.degraded_providers,
      "No degraded providers were reported.",
      "research-report-degraded-providers"
    );

    const statuses = Array.isArray(report.provider_statuses) ? report.provider_statuses : [];
    if (statuses.length === 0) {
      appendText(parent, "p", "No provider-attempt details were reported.", "disclaimer");
      return;
    }

    const table = element("table", "discovery-provider-table research-report-provider-statuses");
    const thead = document.createElement("thead");
    const header = document.createElement("tr");
    ["Provider", "Attempted", "Outcome", "Reason"].forEach((label) => appendText(header, "th", label));
    thead.appendChild(header);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    statuses.forEach((status) => {
      const tr = document.createElement("tr");
      appendText(tr, "td", status && status.provider);
      appendText(tr, "td", status && status.attempted === true ? "yes" : "no");
      appendText(tr, "td", status && status.outcome);
      appendText(tr, "td", status && status.reason, "disclaimer");
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    parent.appendChild(table);
  };

  const renderLayer2 = (block, report) => {
    const details = element("details", "discovery-method-details research-report-layer2");
    details.id = "research-report-layer2";
    const summary = document.createElement("summary");
    summary.textContent = "Evidence and methodology";
    details.appendChild(summary);

    appendText(details, "p", "Researcher audit trail from the structured Research Report contract.", "disclaimer");

    appendText(details, "h4", "Evidence relationships");
    const rows = Array.isArray(report.conclusion_rows) ? report.conclusion_rows : [];
    if (rows.length === 0) {
      appendText(details, "p", "No conclusion-level evidence relationships were returned.", "trust-warning is-critical");
    } else {
      rows.forEach((row) => renderEvidenceRelationship(details, row || {}));
    }

    appendText(details, "h4", "Direct and indirect evidence summaries");
    appendText(details, "h5", "Direct evidence");
    appendText(details, "p", report.direct_evidence_summary, "research-report-evidence-summary");
    appendText(details, "h5", "Indirect / contextual evidence");
    appendText(details, "p", report.indirect_evidence_summary, "research-report-evidence-summary");

    appendText(details, "h4", "Evidence provenance");
    appendText(details, "h5", "Indexed before this research run");
    appendList(
      details,
      report.indexed_before_run_evidence_ids,
      "No previously indexed EvidenceRecord IDs were reported.",
      "research-report-evidence-ids indexed"
    );
    appendText(details, "h5", "Acquired during this research run");
    appendList(
      details,
      report.acquired_during_run_evidence_ids,
      "No newly acquired EvidenceRecord IDs were reported.",
      "research-report-evidence-ids acquired"
    );

    renderProviderCoverage(details, report);

    appendText(details, "h4", "Limitations and missing evidence");
    appendText(details, "h5", "Missing evidence");
    appendList(details, report.missing_evidence, "No report-level missing-evidence items were returned.", "research-report-limitations");
    appendText(details, "h5", "Source-stated limitations carried into the report");
    appendList(details, report.limitations, "No source-stated limitations were carried into this report.", "research-report-limitations");

    appendText(details, "h4", "Research session identity");
    appendText(details, "p", `Session: ${text(report.session_id)}`, "disclaimer");
    appendText(details, "p", `Research state: ${text(report.research_state)}`, "disclaimer");

    block.appendChild(details);
  };

  const hideCompletedPipelineMetadata = (resultNode) => {
    let sibling = resultNode.previousElementSibling;
    while (sibling) {
      sibling.hidden = true;
      sibling = sibling.previousElementSibling;
    }
  };

  const renderLayer1 = (resultNode, researchReport) => {
    if (!resultNode || document.getElementById("research-report-layer1")) return;

    hideCompletedPipelineMetadata(resultNode);
    const block = element("section", "research-report-layer1");
    block.id = "research-report-layer1";
    block.setAttribute("aria-label", "Research Report summary");

    if (!researchReport || !researchReport.available || !researchReport.report) {
      appendText(block, "p", "Structured Research Report unavailable", "trust-label");
      appendText(
        block,
        "p",
        researchReport && researchReport.error_code
          ? `The verified base answer remains available. Structured report status: ${researchReport.error_code}.`
          : "The verified base answer remains available; no structured Research Report was returned.",
        "disclaimer"
      );
      resultNode.prepend(block);
      return;
    }

    const report = researchReport.report;
    appendText(block, "p", "Research Report v1", "trust-label computed");
    appendText(block, "h4", "Bottom line");
    appendText(block, "p", report.bottom_line, "research-report-bottom-line");

    const rows = Array.isArray(report.conclusion_rows) ? report.conclusion_rows : [];
    if (rows.length > 0) {
      appendText(block, "h4", "Conclusions by question dimension");
      const table = element("table", "discovery-provider-table research-report-conclusions");
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      ["Question dimension", "Conclusion", "Certainty", "Missing direct evidence"].forEach((label) => {
        appendText(headerRow, "th", label);
      });
      thead.appendChild(headerRow);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      rows.forEach((row) => renderConclusionRow(tbody, row || {}));
      table.appendChild(tbody);
      block.appendChild(table);
    } else {
      appendText(
        block,
        "p",
        "No dimension-specific conclusion rows were returned by the structured report contract.",
        "trust-warning is-critical"
      );
    }

    renderLayer2(block, report);
    resultNode.prepend(block);
  };

  const MAX_HYDRATE_ATTEMPTS = 4;
  const HYDRATE_RETRY_MS = 1000;

  const hydrate = async (sessionId, resultNode, attempt = 1) => {
    if (!sessionId || !resultNode || resultNode.dataset.reportLayer1Hydrating === "1") return;
    resultNode.dataset.reportLayer1Hydrating = "1";
    let shouldRetry = false;
    try {
      const response = await fetch(`/ask/session/${encodeURIComponent(sessionId)}`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) {
        shouldRetry = true;
        return;
      }
      const payload = await response.json();
      if (!payload.terminal || payload.job_status !== "completed" || !payload.result) {
        shouldRetry = true;
        return;
      }
      renderLayer1(resultNode, payload.result.research_report);
    } catch (_error) {
      shouldRetry = true;
    } finally {
      delete resultNode.dataset.reportLayer1Hydrating;
      if (shouldRetry && attempt < MAX_HYDRATE_ATTEMPTS) {
        window.setTimeout(() => hydrate(sessionId, resultNode, attempt + 1), HYDRATE_RETRY_MS);
      }
    }
  };

  const initialize = () => {
    const session = document.getElementById("async-research-session");
    const resultNode = document.getElementById("async-research-result");
    if (!session || !resultNode) return;
    const sessionId = session.dataset.sessionId;
    if (!sessionId) return;

    if (!resultNode.hidden) {
      hydrate(sessionId, resultNode);
      return;
    }

    const observer = new MutationObserver(() => {
      if (!resultNode.hidden) {
        observer.disconnect();
        hydrate(sessionId, resultNode);
      }
    });
    observer.observe(resultNode, { attributes: true, attributeFilter: ["hidden"] });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
