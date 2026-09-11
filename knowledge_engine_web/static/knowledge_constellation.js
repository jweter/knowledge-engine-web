(() => {
  "use strict";

  const body = document.body;
  if (!body || !body.classList.contains("ke-constellation")) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const coarsePointer = window.matchMedia("(pointer: coarse)").matches;

  const canvas = document.createElement("canvas");
  canvas.id = "knowledge-constellation-field";
  canvas.setAttribute("aria-hidden", "true");
  canvas.setAttribute("role", "presentation");
  body.prepend(canvas);

  const context = canvas.getContext("2d", { alpha: true });
  if (!context) return;

  const hashString = (value) => {
    let hash = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  };

  let seed = hashString(`${window.location.pathname}|Knowledge Engine`);
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };

  const state = {
    width: 0,
    height: 0,
    dpr: 1,
    points: [],
    mouse: { x: -1000, y: -1000, active: false },
    researching: false,
    frame: 0,
  };

  const palette = [
    [114, 232, 255],
    [169, 140, 255],
    [255, 255, 255],
    [255, 210, 122],
  ];

  function pointCount() {
    const area = Math.max(1, state.width * state.height);
    const density = coarsePointer ? 52000 : 39000;
    return Math.max(24, Math.min(coarsePointer ? 44 : 76, Math.round(area / density)));
  }

  function buildPoints() {
    const count = pointCount();
    state.points = Array.from({ length: count }, (_, index) => {
      const cluster = index % 4;
      const clusterX = [0.18, 0.4, 0.67, 0.84][cluster];
      const clusterY = [0.24, 0.72, 0.33, 0.68][cluster];
      const spreadX = 0.18 + random() * 0.18;
      const spreadY = 0.17 + random() * 0.2;
      const x = Math.min(0.97, Math.max(0.03, clusterX + (random() - 0.5) * spreadX));
      const y = Math.min(0.97, Math.max(0.03, clusterY + (random() - 0.5) * spreadY));
      const color = palette[Math.floor(random() * palette.length)];
      return {
        x,
        y,
        phase: random() * Math.PI * 2,
        drift: 0.35 + random() * 0.7,
        radius: 0.7 + random() * 1.65,
        alpha: 0.22 + random() * 0.58,
        color,
      };
    });
  }

  function resize() {
    state.width = Math.max(1, window.innerWidth);
    state.height = Math.max(1, window.innerHeight);
    state.dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(state.width * state.dpr);
    canvas.height = Math.floor(state.height * state.dpr);
    canvas.style.width = `${state.width}px`;
    canvas.style.height = `${state.height}px`;
    context.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);
    buildPoints();
    draw(performance.now());
  }

  function projectedPoint(point, now) {
    const motion = reducedMotion ? 0 : 1;
    const time = now * 0.00004 * point.drift;
    const wobbleX = Math.sin(time * 1.17 + point.phase) * 11 * motion;
    const wobbleY = Math.cos(time + point.phase * 0.73) * 9 * motion;
    let x = point.x * state.width + wobbleX;
    let y = point.y * state.height + wobbleY;

    if (state.mouse.active && !coarsePointer && !reducedMotion) {
      const dx = state.mouse.x - x;
      const dy = state.mouse.y - y;
      const distance = Math.hypot(dx, dy);
      if (distance < 210 && distance > 0) {
        const pull = (1 - distance / 210) * 5.5;
        x += (dx / distance) * pull;
        y += (dy / distance) * pull;
      }
    }

    return { x, y };
  }

  function draw(now) {
    context.clearRect(0, 0, state.width, state.height);
    const projected = state.points.map((point) => projectedPoint(point, now));
    const connectionRange = state.researching ? 176 : 138;
    const baseOpacity = state.researching ? 0.15 : 0.095;

    context.save();
    context.globalCompositeOperation = "lighter";

    for (let left = 0; left < projected.length; left += 1) {
      for (let right = left + 1; right < projected.length; right += 1) {
        const a = projected[left];
        const b = projected[right];
        const distance = Math.hypot(a.x - b.x, a.y - b.y);
        if (distance > connectionRange) continue;

        const closeness = 1 - distance / connectionRange;
        const pulse = reducedMotion
          ? 1
          : 0.78 + Math.sin(now * 0.0012 + left * 0.31 + right * 0.17) * 0.22;
        const alpha = Math.max(0, baseOpacity * closeness * pulse);
        const gradient = context.createLinearGradient(a.x, a.y, b.x, b.y);
        gradient.addColorStop(0, `rgba(91, 220, 255, ${alpha})`);
        gradient.addColorStop(1, `rgba(169, 140, 255, ${alpha * 0.82})`);
        context.strokeStyle = gradient;
        context.lineWidth = state.researching ? 0.88 : 0.68;
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(b.x, b.y);
        context.stroke();

        if (!reducedMotion && state.researching && (left + right) % 17 === 0) {
          const travel = (now * 0.00023 + (left * 0.07 + right * 0.03)) % 1;
          const px = a.x + (b.x - a.x) * travel;
          const py = a.y + (b.y - a.y) * travel;
          context.fillStyle = "rgba(202, 248, 255, 0.7)";
          context.shadowColor = "rgba(114, 232, 255, 0.88)";
          context.shadowBlur = 9;
          context.beginPath();
          context.arc(px, py, 1.35, 0, Math.PI * 2);
          context.fill();
          context.shadowBlur = 0;
        }
      }
    }

    state.points.forEach((point, index) => {
      const { x, y } = projected[index];
      const [r, g, b] = point.color;
      const shimmer = reducedMotion ? 1 : 0.76 + Math.sin(now * 0.0009 + point.phase) * 0.24;
      const alpha = point.alpha * shimmer * (state.researching ? 1.12 : 1);
      const radius = point.radius * (state.researching ? 1.08 : 1);

      context.shadowColor = `rgba(${r}, ${g}, ${b}, ${Math.min(0.8, alpha)})`;
      context.shadowBlur = radius > 1.6 ? 8 : 4;
      context.fillStyle = `rgba(${r}, ${g}, ${b}, ${Math.min(0.92, alpha)})`;
      context.beginPath();
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fill();
      context.shadowBlur = 0;
    });

    context.restore();

    if (!reducedMotion) {
      state.frame = window.requestAnimationFrame(draw);
    }
  }

  function enhanceRealGraphs() {
    document.querySelectorAll(".graph-network svg").forEach((svg) => {
      svg.classList.add("ke-live-graph");
      svg.querySelectorAll("line").forEach((line, index) => {
        line.style.animationDelay = `${-((index * 0.37) % 5.8)}s`;
      });
      svg.querySelectorAll("circle.graph-node").forEach((node, index) => {
        node.style.animationDelay = `${-((index * 0.53) % 4.8)}s`;
      });
    });
  }

  function syncResearchState() {
    const busyButton = document.querySelector('.ask-form button[aria-busy="true"]');
    const runningStatus = document.querySelector(".ask-running-status");
    const statusVisible = Boolean(
      runningStatus &&
      runningStatus.textContent &&
      runningStatus.textContent.trim() &&
      runningStatus.getAttribute("hidden") === null
    );
    const next = Boolean(busyButton || statusVisible);
    if (next === state.researching) return;
    state.researching = next;
    body.classList.toggle("ke-researching", next);
  }

  const observer = new MutationObserver(() => {
    syncResearchState();
    enhanceRealGraphs();
  });

  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["aria-busy", "hidden", "class"],
    childList: true,
    subtree: true,
    characterData: true,
  });

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(resize, 120);
  }, { passive: true });

  if (!coarsePointer) {
    window.addEventListener("pointermove", (event) => {
      state.mouse.x = event.clientX;
      state.mouse.y = event.clientY;
      state.mouse.active = true;
    }, { passive: true });

    document.addEventListener("mouseleave", () => {
      state.mouse.active = false;
    });
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden && state.frame) {
      window.cancelAnimationFrame(state.frame);
      state.frame = 0;
    } else if (!document.hidden && !reducedMotion && !state.frame) {
      state.frame = window.requestAnimationFrame(draw);
    }
  });

  enhanceRealGraphs();
  syncResearchState();
  resize();
})();
