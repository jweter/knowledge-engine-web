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

  const renderLayer1 = (resultNode, researchReport) => {
    if (!resultNode || document.getElementById("research-report-layer1")) return;

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

    resultNode.prepend(block);
  };

  const hydrate = async (sessionId, resultNode) => {
    if (!sessionId || !resultNode || resultNode.dataset.reportLayer1Hydrating === "1") return;
    resultNode.dataset.reportLayer1Hydrating = "1";
    try {
      const response = await fetch(`/ask/session/${encodeURIComponent(sessionId)}`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) return;
      const payload = await response.json();
      if (!payload.terminal || payload.job_status !== "completed" || !payload.result) return;
      renderLayer1(resultNode, payload.result.research_report);
    } catch (_error) {
      // The existing Ask polling surface remains authoritative for transport errors.
      // Layer 1 is additive and must never replace or hide a verified base result.
    } finally {
      delete resultNode.dataset.reportLayer1Hydrating;
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
