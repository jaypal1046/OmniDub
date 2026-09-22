import os
import sys
import json
import shutil
import socket
import threading
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
from typing import List, Dict, Any, Optional, Tuple

from core.panel_classifier import classify_panel_content




HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniDub - Manhwa Panel Classification Review</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0b0f19;
  --surface: #131b2e;
  --surface-hover: #1c2742;
  --border: #243254;
  --primary: #6366f1;
  --primary-hover: #4f46e5;
  --success: #10b981;
  --success-bg: rgba(16, 185, 129, 0.15);
  --warning: #f59e0b;
  --warning-bg: rgba(245, 158, 11, 0.15);
  --danger: #ef4444;
  --danger-bg: rgba(239, 68, 68, 0.15);
  --text: #f8fafc;
  --text-muted: #94a3b8;
}

* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }

body {
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(19, 27, 46, 0.85);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--border);
  padding: 1rem 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
}

.logo-group {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.logo-group h1 {
  font-family: 'Outfit', sans-serif;
  font-size: 1.35rem;
  font-weight: 700;
  background: linear-gradient(135deg, #a5b4fc, #6366f1, #38bdf8);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.stat-pills {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.stat-pill {
  font-size: 0.82rem;
  font-weight: 600;
  padding: 0.35rem 0.8rem;
  border-radius: 9999px;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.stat-pill.include { background: var(--success-bg); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }
.stat-pill.story { background: var(--warning-bg); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.3); }
.stat-pill.exclude { background: var(--danger-bg); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); }

.header-actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

button {
  cursor: pointer;
  border: none;
  outline: none;
  font-weight: 600;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  border-radius: 0.5rem;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-secondary {
  background: var(--surface);
  color: var(--text-muted);
  border: 1px solid var(--border);
  padding: 0.55rem 1rem;
  font-size: 0.88rem;
}

.btn-secondary:hover {
  background: var(--surface-hover);
  color: var(--text);
  border-color: #3b82f6;
}

.btn-primary {
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: #fff;
  padding: 0.6rem 1.4rem;
  font-size: 0.95rem;
  box-shadow: 0 4px 14px 0 rgba(99, 102, 241, 0.39);
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
}

.btn-danger {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
  padding: 0.55rem 1rem;
  font-size: 0.88rem;
}

.btn-danger:hover {
  background: rgba(239, 68, 68, 0.25);
}

main {
  flex: 1;
  padding: 2rem;
  max-width: 1700px;
  margin: 0 auto;
  width: 100%;
}

.controls-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  background: var(--surface);
  padding: 0.85rem 1.25rem;
  border-radius: 0.75rem;
  border: 1px solid var(--border);
}

.filter-group {
  display: flex;
  gap: 0.5rem;
}

.filter-btn {
  padding: 0.4rem 0.85rem;
  font-size: 0.82rem;
  border-radius: 0.4rem;
  background: transparent;
  color: var(--text-muted);
  border: 1px solid transparent;
}

.filter-btn.active, .filter-btn:hover {
  background: var(--surface-hover);
  color: var(--text);
  border-color: var(--border);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
}

.card {
  background: var(--surface);
  border-radius: 0.75rem;
  border: 2px solid var(--border);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: all 0.2s ease;
  position: relative;
}

.card.action-INCLUDE { border-color: rgba(16, 185, 129, 0.5); }
.card.action-STORY_ONLY { border-color: rgba(245, 158, 11, 0.5); }
.card.action-EXCLUDE { border-color: rgba(239, 68, 68, 0.4); opacity: 0.6; }

.card-img-wrap {
  width: 100%;
  height: 380px;
  background: #000;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
}

.card-img-wrap img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  transition: transform 0.3s ease;
}

.card-img-wrap:hover img {
  transform: scale(1.03);
}

.badge-mode {
  position: absolute;
  top: 0.75rem;
  left: 0.75rem;
  font-size: 0.72rem;
  font-weight: 700;
  padding: 0.25rem 0.55rem;
  border-radius: 0.35rem;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.3);
  text-transform: uppercase;
}

.badge-index {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.25rem 0.55rem;
  border-radius: 0.35rem;
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
}

.card-content {
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  flex: 1;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-filename {
  font-size: 0.85rem;
  font-weight: 600;
  color: #cbd5e1;
  word-break: break-all;
}

.card-reason {
  font-size: 0.75rem;
  color: var(--text-muted);
  line-height: 1.3;
}

.dialogue-box {
  background: rgba(11, 15, 25, 0.6);
  padding: 0.6rem;
  border-radius: 0.4rem;
  font-size: 0.75rem;
  color: #94a3b8;
  max-height: 60px;
  overflow-y: auto;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.action-selector {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 0.4rem;
  margin-top: auto;
}

.action-opt {
  padding: 0.5rem 0.2rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 0.4rem;
  text-align: center;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.action-opt:hover {
  background: var(--surface-hover);
  color: var(--text);
}

.action-opt.active-INCLUDE {
  background: var(--success);
  color: #fff;
  border-color: var(--success);
}

.action-opt.active-STORY_ONLY {
  background: var(--warning);
  color: #000;
  border-color: var(--warning);
}

.action-opt.active-EXCLUDE {
  background: var(--danger);
  color: #fff;
  border-color: var(--danger);
}

.toast {
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  background: #1e293b;
  color: #fff;
  padding: 1rem 1.5rem;
  border-radius: 0.5rem;
  border: 1px solid var(--primary);
  box-shadow: 0 10px 25px rgba(0,0,0,0.5);
  display: none;
  z-index: 100;
}
</style>
</head>
<body>

<header>
  <div class="logo-group">
    <h1>🎨 OmniDub Panel Review</h1>
    <div class="stat-pills">
      <div class="stat-pill include">🎬 <span id="count-include">0</span> Video</div>
      <div class="stat-pill story">📖 <span id="count-story">0</span> Story Only</div>
      <div class="stat-pill exclude">❌ <span id="count-exclude">0</span> Skipped</div>
    </div>
  </div>

  <div class="header-actions">
    <button class="btn-secondary" onclick="bulkExcludeBlanks()">⚡ Auto-Clean Ads & Blanks</button>
    <button class="btn-danger" onclick="cancelWorkflow()">✖ Cancel / Exit</button>
    <button class="btn-primary" onclick="submitManifest()">🚀 Approve & Start Rendering</button>
  </div>
</header>

<main>
  <div class="controls-bar">
    <div class="filter-group">
      <button class="filter-btn active" onclick="filterCards('ALL', this)">All (<span id="total-count">0</span>)</button>
      <button class="filter-btn" onclick="filterCards('INCLUDE', this)">🎬 Video Only</button>
      <button class="filter-btn" onclick="filterCards('STORY_ONLY', this)">📖 Story Context Only</button>
      <button class="filter-btn" onclick="filterCards('EXCLUDE', this)">❌ Excluded</button>
    </div>
    <div style="font-size: 0.8rem; color: var(--text-muted);">
      💡 Click on any button below a panel to toggle between Video, Story Only, or Exclude.
    </div>
  </div>

  <div class="grid" id="panel-grid"></div>
</main>

<div class="toast" id="toast"></div>

<script>
let panelsData = [];
let currentFilter = 'ALL';

async function init() {
  const res = await fetch('/api/panels');
  panelsData = await res.json();
  renderGrid();
  updateStats();
}

function updateStats() {
  const inc = panelsData.filter(p => p.action === 'INCLUDE').length;
  const story = panelsData.filter(p => p.action === 'STORY_ONLY').length;
  const exc = panelsData.filter(p => p.action === 'EXCLUDE').length;

  document.getElementById('count-include').innerText = inc;
  document.getElementById('count-story').innerText = story;
  document.getElementById('count-exclude').innerText = exc;
  document.getElementById('total-count').innerText = panelsData.length;
}

function setAction(panelIndex, action) {
  panelsData[panelIndex].action = action;
  const card = document.getElementById('card-' + panelIndex);
  card.className = `card action-${action}`;
  
  const buttons = card.querySelectorAll('.action-opt');
  buttons.forEach(btn => {
    btn.className = 'action-opt';
    if (btn.dataset.action === action) {
      btn.classList.add(`active-${action}`);
    }
  });

  updateStats();
  if (currentFilter !== 'ALL' && currentFilter !== action) {
    card.style.display = 'none';
  }
}

function filterCards(filter, btnEl) {
  currentFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
  if (btnEl) {
    btnEl.classList.add('active');
  }

  panelsData.forEach((p, idx) => {
    const card = document.getElementById('card-' + idx);
    if (!card) return;
    if (filter === 'ALL' || p.action === filter) {
      card.style.display = 'flex';
    } else {
      card.style.display = 'none';
    }
  });
}

function bulkExcludeBlanks() {
  panelsData.forEach((p, idx) => {
    if (p.is_blank || p.is_ad) {
      setAction(idx, 'EXCLUDE');
    }
  });
  showToast('⚡ Excluded all detected blanks & scanlation credits!');
}

function renderGrid() {
  const grid = document.getElementById('panel-grid');
  grid.innerHTML = '';

  panelsData.forEach((p, idx) => {
    const card = document.createElement('div');
    card.id = `card-${idx}`;
    card.className = `card action-${p.action}`;

    card.innerHTML = `
      <div class="card-img-wrap">
        <span class="badge-mode">${p.framing_mode}</span>
        <span class="badge-index">#${idx+1}</span>
        <img src="/image/${encodeURIComponent(p.file)}" loading="lazy" alt="${p.file}" onerror="this.onerror=null;this.alt='Image preview unavailable'">
      </div>
      <div class="card-content">
        <div class="card-header">
          <span class="card-filename">${p.file}</span>
          <span style="font-size:0.75rem;color:#64748b;">${p.height}px</span>
        </div>
        <div class="card-reason">💡 ${p.reason}</div>
        <div class="dialogue-box">${p.ocr_text || '(No dialogue text)'}</div>
        <div class="action-selector">
          <button class="action-opt ${p.action === 'INCLUDE' ? 'active-INCLUDE' : ''}" data-action="INCLUDE" onclick="setAction(${idx}, 'INCLUDE')">🎬 Video</button>
          <button class="action-opt ${p.action === 'STORY_ONLY' ? 'active-STORY_ONLY' : ''}" data-action="STORY_ONLY" onclick="setAction(${idx}, 'STORY_ONLY')">📖 Story</button>
          <button class="action-opt ${p.action === 'EXCLUDE' ? 'active-EXCLUDE' : ''}" data-action="EXCLUDE" onclick="setAction(${idx}, 'EXCLUDE')">❌ Skip</button>
        </div>
      </div>
    `;
    grid.appendChild(card);
  });
}

async function submitManifest() {
  const btn = document.querySelector('.btn-primary');
  if (btn) {
    btn.disabled = true;
    btn.innerText = '⏳ Starting Engine...';
  }

  try {
    const res = await fetch('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(panelsData)
    });
    if (res.ok) {
      document.body.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;text-align:center;background:#0b0f19;">
          <h1 style="font-size:2rem;color:#10b981;margin-bottom:1rem;">🎉 Manifest Approved!</h1>
          <p style="color:#94a3b8;font-size:1.1rem;margin-bottom:1.5rem;">The AI recap engine has started video rendering in your terminal. You can close this tab now.</p>
          <button class="btn-primary" onclick="window.close()">Close Window</button>
        </div>
      `;
    }
  } catch (err) {
    alert('Error submitting manifest: ' + err);
    if (btn) {
      btn.disabled = false;
      btn.innerText = '🚀 Approve & Start Rendering';
    }
  }
}


async function cancelWorkflow() {
  if (confirm('Are you sure you want to cancel and exit?')) {
    await fetch('/api/cancel', { method: 'POST' });
    document.body.innerHTML = `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;text-align:center;background:#0b0f19;">
        <h1 style="font-size:2rem;color:#ef4444;margin-bottom:1rem;">🛑 Workflow Cancelled</h1>
        <p style="color:#94a3b8;font-size:1.1rem;">The terminal process has exited cleanly. You can close this tab.</p>
      </div>
    `;
  }
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.innerText = msg;
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 3000);
}

init();
</script>

</body>
</html>
"""


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class ReviewServerHandler(BaseHTTPRequestHandler):
    panels_dir: str = ""
    panels_data: List[Dict[str, Any]] = []
    submitted_result: Optional[List[Dict[str, Any]]] = None
    server_instance: Optional[ThreadingHTTPServer] = None
    exit_event: Optional[threading.Event] = None
    cancelled: bool = False

    def log_message(self, format, *args):
        # Silence default request logging
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path in ("/", "/index.html"):
            payload = HTML_TEMPLATE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(payload)
        elif path == "/api/panels":
            payload = json.dumps(self.panels_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(payload)
        elif path.startswith("/image/"):
            fname = os.path.basename(path.replace("/image/", ""))
            fpath = os.path.join(self.panels_dir, fname)
            if os.path.exists(fpath) and os.path.isfile(fpath):
                ext = os.path.splitext(fname)[1].lower()
                mime = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/jpeg"
                file_size = os.path.getsize(fpath)
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(file_size))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                with open(fpath, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
        elif path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/submit":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body)
                ReviewServerHandler.submitted_result = data
                resp = b'{"status":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            finally:
                if ReviewServerHandler.exit_event:
                    ReviewServerHandler.exit_event.set()
        elif path == "/api/cancel":
            ReviewServerHandler.cancelled = True
            resp = b'{"status":"cancelled"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            if ReviewServerHandler.exit_event:
                ReviewServerHandler.exit_event.set()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()


def launch_panel_review_web_ui(
    panels_dir: str,
    panel_images: List[str],
    ocr_results: Dict[str, Any],
    slicer_meta_map: Dict[str, Any],
    data_dir: str,
) -> Tuple[List[str], List[str]]:
    """
    Launches a local, self-terminating web UI for 1-click panel approval.
    Returns (active_video_panel_paths, story_context_only_paths).
    """
    port = find_free_port()
    exit_event = threading.Event()

    # Prepare Auto-Classified Initial State
    panels_data: List[Dict[str, Any]] = []
    for idx, img_p in enumerate(panel_images):
        fname = os.path.basename(img_p)
        meta = slicer_meta_map.get(fname, {})
        ocr_text = ocr_results.get(fname, {}).get("ocr_text", "")
        h = meta.get("height", 0)

        # Run CV & OCR Auto-Classifier
        cls_result = classify_panel_content(img_p, ocr_text=ocr_text, height_px=h)

        panels_data.append({
            "panel": idx + 1,
            "file": fname,
            "image_path": img_p,
            "action": cls_result.action,
            "reason": cls_result.reason,
            "is_blank": cls_result.is_blank,
            "is_ad": cls_result.is_ad,
            "ocr_text": ocr_text,
            "height": h,
            "framing_mode": meta.get("framing_mode", "contain")
        })

    ReviewServerHandler.panels_dir = panels_dir
    ReviewServerHandler.panels_data = panels_data
    ReviewServerHandler.submitted_result = None
    ReviewServerHandler.cancelled = False
    ReviewServerHandler.exit_event = exit_event

    server = ThreadingHTTPServer(("127.0.0.1", port), ReviewServerHandler)
    server.daemon_threads = True

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()


    url = f"http://127.0.0.1:{port}"
    print("\n=========================================================================")
    print("🌐 [VISUAL REVIEW] OPENING INTERACTIVE DASHBOARD IN YOUR BROWSER...")
    print(f"👉 Dashboard URL: {url}")
    print("=========================================================================")
    print("💡 Review and classify panels in the web browser, then click 'Approve & Start Rendering'.")
    print("   The server will automatically terminate once approved or cancelled.\n")

    webbrowser.open(url)

    # Block until user submits in browser or cancels
    exit_event.wait()

    # Clean shutdown of server - NO ACTIVE SERVERS LEFT
    server.shutdown()
    server.server_close()
    print("🛑 Local review server shut down cleanly.\n")

    if ReviewServerHandler.cancelled or not ReviewServerHandler.submitted_result:
        print("❌ Workflow cancelled by user from review dashboard.")
        sys.exit(0)

    # Save finalized manifest to disk
    final_manifest = ReviewServerHandler.submitted_result
    manifest_json_p = os.path.join(data_dir, "panel_manifest.json")
    manifest_txt_p = os.path.join(data_dir, "panel_manifest.txt")

    with open(manifest_json_p, "w", encoding="utf-8") as f:
        json.dump(final_manifest, f, indent=2)

    txt_lines = ["# Final Approved Panel Manifest\n"]
    for item in final_manifest:
        txt_lines.append(f"[{item['action']}] {item['file']}  # {item.get('reason', '')}")
    with open(manifest_txt_p, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines))

    # Extract lists
    active_video_panels = [p["image_path"] for p in final_manifest if p["action"] == "INCLUDE"]
    story_context_panels = [p["image_path"] for p in final_manifest if p["action"] == "STORY_ONLY"]

    inc_cnt = len(active_video_panels)
    sty_cnt = len(story_context_panels)
    exc_cnt = len(final_manifest) - inc_cnt - sty_cnt

    print(f"✅ Approved Manifest Summary: 🎬 {inc_cnt} Video Panels | 📖 {sty_cnt} Story Context Panels | ❌ {exc_cnt} Excluded")
    return active_video_panels, story_context_panels
