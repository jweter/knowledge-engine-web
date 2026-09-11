from pathlib import Path


ROOT = Path(__file__).parents[1]
BASE_TEMPLATE = ROOT / "knowledge_engine_web" / "templates" / "base.html"
CONSTELLATION_CSS = ROOT / "knowledge_engine_web" / "static" / "knowledge_constellation.css"
CONSTELLATION_JS = ROOT / "knowledge_engine_web" / "static" / "knowledge_constellation.js"


def test_shared_web_face_loads_constellation_layer() -> None:
    base = BASE_TEMPLATE.read_text(encoding="utf-8")

    assert '<body class="ke-constellation">' in base
    assert 'href="/static/knowledge_constellation.css"' in base
    assert 'src="/static/knowledge_constellation.js"' in base


def test_constellation_motion_is_accessibility_safe() -> None:
    css = CONSTELLATION_CSS.read_text(encoding="utf-8")
    javascript = CONSTELLATION_JS.read_text(encoding="utf-8")

    assert "prefers-reduced-motion: reduce" in css
    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in javascript
    assert 'canvas.setAttribute("aria-hidden", "true")' in javascript
    assert 'canvas.setAttribute("role", "presentation")' in javascript
    assert "pointer-events: none" in css


def test_constellation_layer_is_self_contained() -> None:
    css = CONSTELLATION_CSS.read_text(encoding="utf-8")
    javascript = CONSTELLATION_JS.read_text(encoding="utf-8")

    assert "http://" not in css
    assert "https://" not in css
    assert "fetch(" not in javascript
    assert "XMLHttpRequest" not in javascript


def test_real_graph_enhancement_does_not_add_evidence_nodes() -> None:
    javascript = CONSTELLATION_JS.read_text(encoding="utf-8")

    assert 'document.querySelectorAll(".graph-network svg")' in javascript
    assert 'svg.querySelectorAll("circle.graph-node")' in javascript
    assert "createElementNS" not in javascript
