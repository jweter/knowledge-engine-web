# Knowledge Constellation Web Face

Status: adopted visual direction for the Knowledge Engine Web surface.

## Product intent

Knowledge Engine should not look like a generic admin dashboard. Its public face should make the central product idea visible: isolated evidence becomes useful when trustworthy connections are discovered, preserved, and inspected.

The visual metaphor is a hybrid of:

- neurons forming new synaptic connections;
- stars forming constellations;
- galaxies resolving from scattered points into coherent structure;
- scientific evidence becoming a navigable knowledge graph.

The intended feeling is **quietly magical, precise, and scientific**, not decorative sci-fi.

## Non-negotiable rule: the magic must be earned

Visual effects must never imply scientific evidence, confidence, progress, or relationships that do not exist.

The ambient background constellation is explicitly decorative and is hidden from assistive technology. Meaningful graph animation is applied only to the existing reviewed relationship SVG. Research-state intensity is tied to real Ask UI state (`aria-busy` / the actual running-status surface), never a fabricated percentage or fake stage.

Existing semantic relationship colors, warning states, evidence provenance, provider degradation, uncertainty, and Research ISA release gates remain authoritative.

## Visual system

### 1. Cosmic shell

The shared site shell uses a deep-space field with translucent scientific-instrument panels, restrained cyan/violet aurora light, fine star points, and a low-density neural/constellation mesh.

It must remain readable first. Pages are still information surfaces, not full-screen animation demos.

### 2. Real relationship graph as centerpiece

The home-page hero already renders a real, source-linked slice of the grounding-verified relationship graph. That graph is the strongest visual asset we have because it is both beautiful and truthful.

The Constellation layer gives its nodes a soft stellar glow and lets reviewed edges breathe subtly. It does not add fake evidence nodes or replace relationship-type colors.

### 3. Research activity as connection formation

When Ask is genuinely performing asynchronous Research, the ambient network becomes slightly denser and signal particles travel along a subset of decorative connections. This should feel like the engine is finding and joining pieces of knowledge.

The effect stops when the real running state stops. It does not claim that an individual visual line represents a retrieved paper or verified claim.

### 4. Glass observatory surfaces

Header, primary content, evidence cards, stats, report cards, and controls use restrained translucent panels with luminous borders. The visual hierarchy should resemble an observatory or scientific instrument rather than a game HUD.

### 5. Motion policy

Motion is ambient and slow. `prefers-reduced-motion` disables continuous CSS motion and causes the canvas layer to render as a static field. Coarse-pointer/mobile devices use fewer points to reduce GPU/CPU work.

No interaction or evidence inspection depends on animation.

## Implemented first slice

The first slice is intentionally architecture-safe and frontend-only:

- `knowledge_engine_web/static/knowledge_constellation.css`
  - deep-space/glass visual language;
  - landing hero and reviewed graph treatment;
  - Ask/research-state treatment;
  - mobile, reduced-motion, and increased-contrast accommodations.
- `knowledge_engine_web/static/knowledge_constellation.js`
  - self-contained, deterministic ambient constellation canvas;
  - no external assets or network calls;
  - reviewed graph animation hooks;
  - real Ask busy/running-state observation.
- `knowledge_engine_web/templates/base.html`
  - loads the visual layer on the shared Web face.

This slice does **not** change evidence semantics, the Research Report contract, retrieval, verification, source provenance, or release gates.

## Next visual phases

The visual direction should evolve with the real product instead of inventing a parallel decorative simulation.

1. **Evidence constellation view** — cluster real Evidence Records by resolved concept/topic and show the inspected source behind every star.
2. **Connection birth** — when a new reviewed relationship is actually persisted, animate that real edge into the graph rather than only refreshing the finished view.
3. **Research journey** — progressively introduce real acquired sources during a Research Session while maintaining a strict distinction between acquired, extracted, promoted, and verified states.
4. **Contradiction nebulae** — make support, qualification, contradiction, and supersession patterns spatially legible without flattening them into one score.
5. **Zoom from answer to evidence** — allow a Layer 1 conclusion to visually trace into its exact Layer 2 evidence constellation and source detail.
6. **Concept galaxies** — use real connected components / semantic clusters once the Core graph has enough validated density to justify the metaphor.

## Acceptance criteria

A visual release in this direction is successful when:

- the site feels recognizably like Knowledge Engine rather than a generic FastAPI UI;
- the home page communicates "knowledge becoming connected" before the user reads the architecture description;
- Ask becomes more visually alive while real Research is running without implying fake progress;
- the reviewed relationship graph remains semantically correct and inspectable;
- critical/degraded states remain at least as visually prominent as before;
- keyboard use, text selection, links, forms, evidence inspection, and source navigation remain unaffected;
- reduced-motion users receive a stable non-animated experience;
- mobile performance remains acceptable and no external visual dependency is introduced.
