/**
 * Aegis Assistant — Overlay hint poller.
 * Fetches /hint from the runtime server every 500ms
 * and updates the overlay UI.
 */

const HINT_URL = "http://127.0.0.1:5000/hint";
const POLL_MS = 500;

const hintEl       = document.getElementById("hint-text");
const statusEl     = document.getElementById("status");
const confFill     = document.getElementById("confidence-fill");
const confLabel    = document.getElementById("confidence-label");

let consecutiveErrors = 0;

async function fetchHint() {
  try {
    const res = await fetch(HINT_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    consecutiveErrors = 0;

    // Update hint text
    hintEl.textContent = data.hint || "…";

    // Update confidence
    const conf = data.confidence || 0;
    const pct = Math.round(conf * 100);
    confFill.style.width = `${pct}%`;
    confLabel.textContent = conf > 0 ? `${pct}%` : "—";

    // Update status
    if (data.stale) {
      statusEl.textContent = "● Waiting for GSI…";
      statusEl.className = "status stale";
    } else {
      statusEl.textContent = "● Connected";
      statusEl.className = "status connected";
    }
  } catch (err) {
    consecutiveErrors++;
    if (consecutiveErrors >= 3) {
      statusEl.textContent = "● Disconnected";
      statusEl.className = "status disconnected";
      confFill.style.width = "0%";
      confLabel.textContent = "—";
    }
  }
}

setInterval(fetchHint, POLL_MS);
fetchHint();
