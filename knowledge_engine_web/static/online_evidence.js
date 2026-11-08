(function () {
  "use strict";
  var form = document.getElementById("online-evidence-form");
  if (!form) { return; }
  var input = document.getElementById("online-evidence-question");
  var submit = document.getElementById("online-evidence-submit");
  var progress = document.getElementById("online-evidence-progress");
  var errorEl = document.getElementById("online-evidence-error");
  var results = document.getElementById("online-evidence-results");
  var summary = document.getElementById("online-evidence-summary");
  var sources = document.getElementById("online-evidence-sources");
  var claims = document.getElementById("online-evidence-claims");
  var claimsEmpty = document.getElementById("online-evidence-claims-empty");

  function el(tag, text, cls) {
    var n = document.createElement(tag);
    if (text !== undefined && text !== null) { n.textContent = text; }
    if (cls) { n.className = cls; }
    return n;
  }
  function safeHref(url) {
    try {
      var u = new URL(url);
      return (u.protocol === "https:" || u.protocol === "http:") ? u.href : null;
    } catch (e) { return null; }
  }
  function renderReport(report) {
    var section = document.getElementById("online-evidence-report");
    if (!report) { section.hidden = true; return; }
    document.getElementById("online-evidence-bottom-line").textContent = report.bottom_line;
    var rows = document.getElementById("online-evidence-conclusions");
    rows.replaceChildren();
    report.conclusion_rows.forEach(function (row) {
      var li = el("li", null, "ask-result-card");
      li.appendChild(el("p", row.conclusion));
      li.appendChild(el("p", "Certainty: " + row.certainty + " — " + row.certainty_rationale, "disclaimer"));
      li.appendChild(el("p", "Supporting excerpts: " + (row.supporting_evidence_ids.join(", ") || "none") +
        "; contradicting or null: " + (row.contradicting_or_null_evidence_ids.join(", ") || "none"), "disclaimer"));
      rows.appendChild(li);
    });
    var missing = document.getElementById("online-evidence-missing");
    missing.replaceChildren();
    report.missing_evidence.concat(report.limitations).forEach(function (t) {
      missing.appendChild(el("li", t));
    });
    section.hidden = false;
  }
  var stageLabels = {
    completed: "completed",
    failed_closed: "failed closed (evidence still shown, no analysis)"
  };
  function renderStages(stages) {
    var list = document.getElementById("online-evidence-stages");
    list.replaceChildren();
    (stages || []).forEach(function (st) {
      list.appendChild(el("li", st.label + " — " + (stageLabels[st.status] || st.status) +
        " (" + (st.elapsed_ms / 1000).toFixed(1) + " s)"));
    });
    list.parentElement.hidden = !(stages && stages.length);
  }
  var timer = null;
  function stopTimer() { if (timer) { clearInterval(timer); timer = null; } }
  function render(data) {
    renderStages(data.stages);
    renderReport(data.report);
    var s = data.source_status_summary;
    var c = s.status_counts;
    summary.textContent = s.source_count + " source(s) returned (" + c.retrieved +
      " retrieved, " + c.unavailable + " unavailable, " + c.not_permitted +
      " not permitted, " + c.failed + " failed). Counts cover returned sources only, " +
      "not exhaustive provider coverage. Search run: " + data.search_run_id + ".";
    sources.replaceChildren();
    var byId = {};
    data.evidence.sources.forEach(function (src) {
      byId[src.source_id] = src;
      var li = el("li", null, "ask-result-card");
      li.id = "src-" + src.source_id;
      li.appendChild(el("h3", src.title || src.url));
      var href = safeHref(src.url);
      var p = el("p", null, "disclaimer");
      p.appendChild(document.createTextNode(src.provider + " · " + src.status + " · retrieved " + src.retrieved_at + " · "));
      if (href) {
        var a = el("a", src.url); a.href = href; a.rel = "noopener noreferrer"; p.appendChild(a);
      } else { p.appendChild(document.createTextNode(src.url)); }
      li.appendChild(p);
      if (src.failure_reason) { li.appendChild(el("p", "Not usable as evidence: " + src.failure_reason, "disclaimer")); }
      if (src.content_sha256) { li.appendChild(el("p", "Content SHA-256: " + src.content_sha256, "disclaimer")); }
      sources.appendChild(li);
    });
    var excerpts = {};
    data.evidence.excerpts.forEach(function (x) { excerpts[x.excerpt_id] = x; });
    claims.replaceChildren();
    claimsEmpty.hidden = data.evidence.claims.length !== 0;
    data.evidence.claims.forEach(function (claim) {
      var li = el("li", null, "ask-result-card");
      li.appendChild(el("p", "Claim (" + claim.status + ")", "trust-label"));
      li.appendChild(el("p", claim.text));
      (claim.citations || []).forEach(function (cit) {
        var ex = excerpts[cit.excerpt_id];
        var src = ex ? byId[ex.source_id] : null;
        var q = el("blockquote", ex ? ex.text : "(cited excerpt not returned)");
        li.appendChild(q);
        if (src) {
          var link = el("a", "Source: " + (src.title || src.url));
          link.href = "#src-" + src.source_id;
          li.appendChild(link);
        }
      });
      claims.appendChild(li);
    });
    results.hidden = false;
  }
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var question = input.value.trim();
    errorEl.textContent = "";
    if (!question) { errorEl.textContent = "Enter a research question."; input.focus(); return; }
    results.hidden = true;
    submit.disabled = true;
    var t0 = Date.now();
    var base = "Discovering, retrieving and validating online sources in one backend run (stage detail is reported when it finishes; this can take up to a couple of minutes)";
    progress.textContent = base + "… 0 s elapsed.";
    stopTimer();
    timer = setInterval(function () {
      progress.textContent = base + "… " + Math.round((Date.now() - t0) / 1000) + " s elapsed.";
    }, 1000);
    fetch("/research/online-evidence", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question })
    }).then(function (resp) {
      return resp.json().then(function (body) { return { ok: resp.ok, body: body }; });
    }).then(function (r) {
      stopTimer();
      if (!r.ok) {
        errorEl.textContent = typeof r.body.detail === "string" ? r.body.detail : "The request could not be completed.";
        progress.textContent = "";
        return;
      }
      progress.textContent = "Retrieval finished. This is retrieval only, not a Research Report.";
      render(r.body);
    }).catch(function () {
      stopTimer();
      progress.textContent = "";
      errorEl.textContent = "Network error. No evidence was retrieved.";
    }).then(function () { submit.disabled = false; });
  });
})();
