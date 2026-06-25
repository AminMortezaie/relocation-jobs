/** Full-screen circular loader — progress only moves forward. */

const RING_R = 24;
const RING_LEN = 2 * Math.PI * RING_R;

let depth = 0;
let displayPct = 0;
let targetPct = 0;
let rafId = null;
let finishTimer = null;

function elements() {
  return {
    root: document.getElementById("screenLoader"),
    arc: document.getElementById("screenLoaderArc"),
    pct: document.getElementById("screenLoaderPct"),
    label: document.getElementById("screenLoaderLabel"),
    ring: document.getElementById("screenLoaderRing"),
  };
}

function paint(pct) {
  const value = Math.max(0, Math.min(100, pct));
  const { arc, pct: pctEl, ring } = elements();
  if (arc) {
    arc.style.strokeDasharray = `${RING_LEN}`;
    arc.style.strokeDashoffset = `${RING_LEN * (1 - value / 100)}`;
  }
  if (pctEl) pctEl.textContent = value >= 8 ? `${Math.round(value)}%` : "";
  ring?.setAttribute("aria-valuenow", String(Math.round(value)));
}

function stopLoop() {
  if (rafId != null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
}

function bumpTarget(pct) {
  targetPct = Math.max(targetPct, Math.min(pct, 100));
}

function tick() {
  if (displayPct < targetPct) {
    const gap = targetPct - displayPct;
    const step = Math.max(0.45, gap * 0.14);
    displayPct = Math.min(targetPct, displayPct + step);
    paint(displayPct);
  }

  if (depth > 0 && targetPct < 90) {
    bumpTarget(targetPct + 0.22);
  }

  if (depth > 0 || displayPct < 99.8) {
    rafId = requestAnimationFrame(tick);
    return;
  }
  rafId = null;
}

function startLoop() {
  if (rafId != null) return;
  rafId = requestAnimationFrame(tick);
}

function resetSession() {
  stopLoop();
  if (finishTimer) {
    clearTimeout(finishTimer);
    finishTimer = null;
  }
  displayPct = 0;
  targetPct = 0;
  paint(0);
}

export function isScreenLoadActive() {
  return depth > 0;
}

export function beginScreenLoad(label = "Loading…") {
  depth += 1;
  const { root, label: labelEl } = elements();
  if (!root) return;

  if (depth === 1) {
    resetSession();
    if (labelEl) labelEl.textContent = label;
    root.hidden = false;
    root.classList.remove("is-done");
    document.body.classList.add("screen-loading");
    requestAnimationFrame(() => root.classList.add("is-visible"));
    bumpTarget(12);
    startLoop();
  } else if (labelEl) {
    labelEl.textContent = label;
    bumpTarget(displayPct + 4);
  }
}

export function setScreenLoadProgress(pct) {
  bumpTarget(pct);
  startLoop();
}

export function endScreenLoad() {
  depth = Math.max(0, depth - 1);
  if (depth > 0) return;

  bumpTarget(100);
  startLoop();

  const { root } = elements();
  if (!root) return;

  const finalize = () => {
    root.classList.add("is-done");
    root.classList.remove("is-visible");
    document.body.classList.remove("screen-loading");
    finishTimer = window.setTimeout(() => {
      if (depth === 0) {
        root.hidden = true;
        root.classList.remove("is-done");
        resetSession();
      }
      finishTimer = null;
    }, 400);
  };

  const waitComplete = () => {
    if (displayPct >= 99.5) {
      finalize();
      return;
    }
    requestAnimationFrame(waitComplete);
  };
  waitComplete();
}
