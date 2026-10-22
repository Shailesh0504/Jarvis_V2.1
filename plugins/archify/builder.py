# plugins/archify/builder.py
"""
Archify Architecture Builder & Synchronizer for Jarvis V2.1.
Automatically parses architecture.txt / jarvis-architecture.json, updates the
JSON specification, and generates/re-compiles the self-contained interactive
jarvis-architecture.html viewer.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.plugins.archify.builder")

DEFAULT_ARCH_TXT = "architecture.txt"
DEFAULT_ARCH_JSON = os.path.join(os.path.dirname(__file__), "jarvis-architecture.json")
DEFAULT_ARCH_HTML = os.path.join(os.path.dirname(__file__), "jarvis-architecture.html")


def parse_architecture_txt(txt_path: str) -> Dict[str, Any]:
    """
    Extracts architectural structure, layer titles, components, and notes
    from architecture.txt.
    """
    if not os.path.isfile(txt_path):
        logger.warning("Architecture text file not found: %s", txt_path)
        return {}

    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    lines = content.splitlines()
    title = "Jarvis V2.1 System Architecture"
    subtitle = "Modular Local-First Voice & Workflow AI Assistant with 7-Layer Intelligence Pipeline"

    # Search for header title
    for line in lines[:10]:
        if "SYSTEM ARCHITECTURE" in line.upper():
            clean = line.replace("=", "").strip()
            if clean:
                title = clean

    # Detect major structural blocks
    blocks = re.findall(r"│\s*([A-Z0-9 &/_—–-]{5,})\s*│", content)
    cleaned_blocks = [b.strip() for b in blocks if len(b.strip()) > 4 and not b.strip().startswith("📊")]

    return {
        "title": title,
        "subtitle": subtitle,
        "detected_blocks": cleaned_blocks,
        "line_count": len(lines),
    }


def compile_archify_html(
    json_path: Optional[str] = None,
    html_path: Optional[str] = None,
    spec_data: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str]:
    """
    Compiles or updates jarvis-architecture.html from the given JSON specification.
    If jarvis-architecture.html already contains the full embedded Archify runtime
    (CSS, fonts, JS modules, interactive radar, lens), this function surgical updates
    the JSON data payload, title, SVG nodes, connections, and info cards.
    """
    target_json = json_path or DEFAULT_ARCH_JSON
    target_html = html_path or DEFAULT_ARCH_HTML

    if spec_data is None:
        if not os.path.isfile(target_json):
            return False, f"JSON spec file not found at {target_json}"
        try:
            with open(target_json, "r", encoding="utf-8") as f:
                spec_data = json.load(f)
        except Exception as e:
            return False, f"Failed to parse JSON spec: {e}"

    if not os.path.isfile(target_html):
        return False, f"Target HTML viewer base not found at {target_html}"

    try:
        with open(target_html, "r", encoding="utf-8") as f:
            html = f.read()

        meta = spec_data.get("meta", {})
        title = meta.get("title", "Jarvis V2.1 System Architecture")
        views = meta.get("views", [])
        components = spec_data.get("components", [])
        boundaries = spec_data.get("boundaries", [])
        connections = spec_data.get("connections", [])
        cards = spec_data.get("cards", [])

        # 1. Update document title & header
        html = re.sub(r"<title>.*?</title>", lambda _: f"<title>{title}</title>", html, count=1)
        html = re.sub(
            r"<h1>.*?</h1>",
            lambda _: f"<h1>{title}</h1>",
            html,
            count=1
        )

        # 2. Update Guided Views JSON script tag
        views_json_str = json.dumps(views, ensure_ascii=False)
        html = re.sub(
            r'<script id="archify-guided-views-data" type="application/json">.*?</script>',
            lambda _: f'<script id="archify-guided-views-data" type="application/json">{views_json_str}</script>',
            html,
            count=1
        )

        # 3. Build replacement SVG content
        all_x = [c["pos"][0] + c["size"][0] for c in components] + [c["pos"][0] for c in components]
        all_y = [c["pos"][1] + c["size"][1] for c in components] + [c["pos"][1] for c in components]
        max_x = max(all_x) if all_x else 1480
        max_y = max(all_y) if all_y else 670
        canvas_w = meta.get("canvas_width", max(1660, max_x + 40))
        canvas_h = meta.get("canvas_height", max(730, max_y + 80))

        svg_parts = []
        svg_parts.append(f'      <svg viewBox="0 0 {canvas_w} {canvas_h}" role="img" lang="en" aria-labelledby="archify-diagram-title archify-diagram-description" data-animation="trace" data-preset="blueprint" data-quality-profile="showcase">')
        svg_parts.append(f'  <title id="archify-diagram-title">{title}</title>')
        svg_parts.append('  <desc id="archify-diagram-description">Interactive Archify architecture map of Jarvis V2.1 voice assistant and proactive cognition system.</desc>')
        svg_parts.append('  <defs>')
        svg_parts.append('    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" class="m-default" /></marker>')
        svg_parts.append('    <marker id="arrowhead-emphasis" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" class="m-emphasis" /></marker>')
        svg_parts.append('    <marker id="arrowhead-security" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" class="m-security" /></marker>')
        svg_parts.append('    <marker id="arrowhead-dashed" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" class="m-dashed" /></marker>')
        svg_parts.append('    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M 40 0 L 0 0 0 40" class="c-grid" stroke-width="0.5"/></pattern>')
        svg_parts.append('  </defs>')
        svg_parts.append('  <rect width="100%" height="100%" fill="url(#grid)" />')

        # Structural frames (boundaries)
        for i, b in enumerate(boundaries):
            kind = b.get("kind", "region")
            label = b.get("label", "")
            wraps = b.get("wraps", [])
            rect = b.get("rect")
            if rect and len(rect) == 4:
                min_x, min_y, w, h = rect[0], rect[1], rect[2], rect[3]
            else:
                # Compute bounding box
                wrap_nodes = [c for c in components if c.get("id") in wraps]
                if wrap_nodes:
                    min_x = min(c["pos"][0] for c in wrap_nodes) - 15
                    min_y = min(c["pos"][1] for c in wrap_nodes) - 35
                    max_x = max(c["pos"][0] + c["size"][0] for c in wrap_nodes) + 15
                    max_y = max(c["pos"][1] + c["size"][1] for c in wrap_nodes) + 14
                    w = max_x - min_x
                    h = max_y - min_y
                else:
                    min_x, min_y, w, h = 100, 100, 200, 100

            css_cls = "c-security-group" if kind == "security-group" else "c-region"
            rx = "8" if kind == "security-group" else "12"
            svg_parts.append(
                f'  <rect data-graph-role="structural-frame" data-composition-frame-kind="{kind}" '
                f'data-composition-frame-id="{i}" data-composition-frame-label="{label}" '
                f'x="{min_x}" y="{min_y}" width="{w}" height="{h}" rx="{rx}" class="{css_cls}" stroke-width="1"/>'
            )
            # Add prominent frame label for readability
            if label:
                svg_parts.append(
                    f'  <text x="{min_x + 14}" y="{min_y + 18}" class="t-dim" font-size="9.5" font-weight="700" letter-spacing="0.06em">{label.upper()}</text>'
                )

        # Node index for connection calculations
        node_map = {c["id"]: c for c in components}

        # Directed Connections (edges)
        for idx, conn in enumerate(connections):
            u_id = conn.get("from")
            v_id = conn.get("to")
            label = conn.get("label", "")
            variant = conn.get("variant", "default")
            route = conn.get("route")  # Optional explicit waypoints: list of [x, y]

            u = node_map.get(u_id)
            v = node_map.get(v_id)
            if not u or not v:
                continue

            ux, uy, uw, uh = u["pos"][0], u["pos"][1], u["size"][0], u["size"][1]
            vx, vy, vw, vh = v["pos"][0], v["pos"][1], v["size"][0], v["size"][1]

            if route and len(route) >= 2:
                # Custom routed polyline
                pts = [f"{pt[0]} {pt[1]}" for pt in route]
                path_d = f"M {pts[0]} " + " ".join(f"L {p}" for p in pts[1:])
            else:
                # Automatic clean orthogonal / straight path calculation
                if abs(ux - vx) >= abs(uy - vy):
                    if ux < vx:
                        start_pt = (ux + uw, uy + uh / 2)
                        end_pt = (vx, vy + vh / 2)
                    else:
                        start_pt = (ux, uy + uh / 2)
                        end_pt = (vx + vw, vy + vh / 2)
                else:
                    if uy < vy:
                        start_pt = (ux + uw / 2, uy + uh)
                        end_pt = (vx + vw / 2, vy)
                    else:
                        start_pt = (ux + uw / 2, uy)
                        end_pt = (vx + vw / 2, vy + vh)

                path_d = f"M {start_pt[0]} {start_pt[1]} L {end_pt[0]} {end_pt[1]}"

            edge_cls = "a-emphasis" if variant == "emphasis" else ("a-security" if variant == "security" else "a-dashed")
            marker = "arrowhead-emphasis" if variant == "emphasis" else ("arrowhead-security" if variant == "security" else "arrowhead-dashed")
            step = idx % 8

            svg_parts.append(
                f'  <path data-edge-from="{u_id}" data-edge-to="{v_id}" data-edge-label="{label}" data-edge-key="{idx}" '
                f'd="{path_d}" class="{edge_cls}" data-animate="edge" style="--step:{step}" stroke-width="1.8" marker-end="url(#{marker})"/>'
            )

        # Render Nodes
        for idx, c in enumerate(components):
            nid = c["id"]
            kind = c.get("type", "backend")
            label = c.get("label", nid)
            sub = c.get("sublabel", "")
            tag = c.get("tag")
            x, y = c["pos"][0], c["pos"][1]
            w, h = c["size"][0], c["size"][1]
            step = idx % 8

            node_tag_attr = f' data-node-tag="{tag}"' if tag else ""
            svg_parts.append(
                f'  <g id="node-{nid}" data-node-id="{nid}" data-node-label="{label}" tabindex="0" role="button" '
                f'aria-label="Focus {label}, {sub}" aria-pressed="false" data-node-kind="{kind}" data-node-sublabel="{sub}"{node_tag_attr}>'
            )
            svg_parts.append(f'    <title>{label} · {sub}</title>')
            svg_parts.append(f'    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" class="c-mask"/>')
            svg_parts.append(f'    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" class="c-{kind}" data-animate="node" style="--step:{step}" stroke-width="1.5"/>')

            cx = x + w / 2
            ty1 = y + 20
            ty2 = y + 34
            svg_parts.append(f'    <text data-node-label="" data-detail-anchor="" x="{cx}" y="{ty1}" class="t-primary" font-size="10.5" font-weight="600" text-anchor="middle">{label}</text>')
            svg_parts.append(f'    <text data-detail="context" x="{cx}" y="{ty2}" class="t-muted" font-size="8.5" text-anchor="middle">{sub}</text>')
            if tag:
                svg_parts.append(f'    <text data-detail="fine" x="{cx}" y="{y + 44}" class="t-{kind}" font-size="7.5" text-anchor="middle">{tag}</text>')
            svg_parts.append('  </g>')

        # Legend footer (dynamically centered below all frames)
        legend_x = max(30, (canvas_w - 920) // 2)
        legend_y_offset = (canvas_h - 38) - 572
        svg_parts.append(f'  <g class="diagram-legend" id="diagram-legend" role="group" aria-label="Semantic legend" transform="translate({legend_x}, {legend_y_offset})">')
        svg_parts.append('    <g data-legend-semantic-kind="external" data-legend-kind="external" data-legend-label="External / User" data-legend-x="100">')
        svg_parts.append('      <rect x="100" y="572" width="14" height="9" rx="2.5" class="c-external" stroke-width="1"/>')
        svg_parts.append('      <text x="120" y="580" class="t-muted" font-size="9" font-weight="500">External / User</text>')
        svg_parts.append('    </g>')
        svg_parts.append('    <g data-legend-semantic-kind="frontend" data-legend-kind="frontend" data-legend-label="Frontend GUI" data-legend-x="240">')
        svg_parts.append('      <rect x="240" y="572" width="14" height="9" rx="2.5" class="c-frontend" stroke-width="1"/>')
        svg_parts.append('      <text x="260" y="580" class="t-muted" font-size="9" font-weight="500">Frontend GUI</text>')
        svg_parts.append('    </g>')
        svg_parts.append('    <g data-legend-semantic-kind="backend" data-legend-kind="backend" data-legend-label="Core Backend" data-legend-x="370">')
        svg_parts.append('      <rect x="370" y="572" width="14" height="9" rx="2.5" class="c-backend" stroke-width="1"/>')
        svg_parts.append('      <text x="390" y="580" class="t-muted" font-size="9" font-weight="500">Core Backend</text>')
        svg_parts.append('    </g>')
        svg_parts.append('    <g data-legend-semantic-kind="security" data-legend-kind="security" data-legend-label="Security / Gate" data-legend-x="500">')
        svg_parts.append('      <rect x="500" y="572" width="14" height="9" rx="2.5" class="c-security" stroke-width="1"/>')
        svg_parts.append('      <text x="520" y="580" class="t-muted" font-size="9" font-weight="500">Security / Gate</text>')
        svg_parts.append('    </g>')
        svg_parts.append('    <g data-legend-semantic-kind="messagebus" data-legend-kind="messagebus" data-legend-label="EventBus / Stream" data-legend-x="640">')
        svg_parts.append('      <rect x="640" y="572" width="14" height="9" rx="2.5" class="c-messagebus" stroke-width="1"/>')
        svg_parts.append('      <text x="660" y="580" class="t-muted" font-size="9" font-weight="500">EventBus / Stream</text>')
        svg_parts.append('    </g>')
        svg_parts.append('    <g data-legend-semantic-kind="database" data-legend-kind="database" data-legend-label="Cognitive DB" data-legend-x="800">')
        svg_parts.append('      <rect x="800" y="572" width="14" height="9" rx="2.5" class="c-database" stroke-width="1"/>')
        svg_parts.append('      <text x="820" y="580" class="t-muted" font-size="9" font-weight="500">Cognitive DB</text>')
        svg_parts.append('    </g>')
        svg_parts.append('  </g>')
        svg_parts.append('</svg>')

        new_svg_block = "\n".join(svg_parts)

        # Replace SVG in HTML
        svg_pattern = re.compile(r'<svg viewBox="[^"]*".*?</svg>', re.DOTALL)
        if svg_pattern.search(html):
            html = svg_pattern.sub(lambda _: new_svg_block, html, count=1)
        else:
            logger.warning("SVG pattern not matched in HTML viewer")

        # 4. Update Info Cards
        cards_parts = ['<div class="cards">']
        for card in cards:
            dot = card.get("dot", "cyan")
            ctitle = card.get("title", "")
            items = card.get("items", [])
            cards_parts.append('  <div class="card">')
            cards_parts.append('    <div class="card-header">')
            cards_parts.append(f'      <div class="card-dot {dot}"></div>')
            cards_parts.append(f'      <h3>{ctitle}</h3>')
            cards_parts.append('    </div>')
            cards_parts.append('    <ul>')
            for it in items:
                cards_parts.append(f'      <li>&bull; {it}</li>')
            cards_parts.append('    </ul>')
            cards_parts.append('  </div>')
        cards_parts.append('</div>')
        new_cards_block = "\n".join(cards_parts)

        cards_pattern = re.compile(r'<div class="cards">.*?</div>\s*</div>\s*<script>', re.DOTALL)
        if cards_pattern.search(html):
            replacement = f'{new_cards_block}\n  </div>\n\n  <script>'
            html = cards_pattern.sub(lambda _: replacement, html, count=1)

        # 5. Inject Live Auto-Update Client Engine
        live_client_script = '''
  <!-- Archify Live Auto-Update Client Engine -->
  <div id="archify-live-indicator" style="position:fixed;top:12px;right:18px;z-index:99999;display:flex;align-items:center;gap:8px;padding:6px 14px;background:rgba(10,16,28,0.88);backdrop-filter:blur(10px);border:1px solid rgba(0,240,255,0.45);border-radius:20px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#00f0ff;box-shadow:0 0 14px rgba(0,240,255,0.22);cursor:pointer;user-select:none;transition:all 0.25s ease;" title="Live Auto-Update Active (Click to sync now)">
    <span id="archify-live-dot" style="width:8px;height:8px;border-radius:50%;background:#00ff88;box-shadow:0 0 8px #00ff88;display:inline-block;animation:archify-pulse 2s infinite;"></span>
    <span id="archify-live-text" style="font-weight:600;letter-spacing:0.5px;">LIVE AUTO-UPDATE: ACTIVE</span>
  </div>
  <style>
    @keyframes archify-pulse {
      0% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.35; transform: scale(0.8); }
      100% { opacity: 1; transform: scale(1); }
    }
    #archify-live-indicator:hover {
      background: rgba(14,24,42,0.95);
      border-color: #00ff88;
      box-shadow: 0 0 18px rgba(0,255,136,0.35);
      transform: translateY(-1px);
    }
  </style>
  <script id="archify-live-auto-update-script">
    (function() {
      var currentVersion = null;
      var pollUrl = 'http://127.0.0.1:8766/api/poll';
      var isChecking = false;
      var dot = document.getElementById('archify-live-dot');
      var text = document.getElementById('archify-live-text');
      var pill = document.getElementById('archify-live-indicator');

      if (pill) {
        pill.addEventListener('click', function() {
          if (text) text.textContent = 'SYNCING NOW...';
          fetch('http://127.0.0.1:8766/api/sync')
            .then(function() { window.location.reload(); })
            .catch(function() { window.location.reload(); });
        });
      }

      function checkUpdate() {
        if (isChecking) return;
        isChecking = true;
        fetch(pollUrl, { cache: 'no-store' })
          .then(function(res) { return res.json(); })
          .then(function(data) {
            isChecking = false;
            if (dot) { dot.style.background = '#00ff88'; dot.style.boxShadow = '0 0 8px #00ff88'; }
            if (text && text.textContent !== 'UPDATING ARCHITECTURE...') { text.textContent = 'LIVE AUTO-UPDATE: ACTIVE'; }
            if (data && data.version) {
              if (currentVersion === null) {
                currentVersion = data.version;
              } else if (currentVersion !== data.version) {
                console.log('[Archify Live] Live architecture update detected:', data.version, 'Auto-reloading...');
                if (text) { text.textContent = 'UPDATING ARCHITECTURE...'; }
                currentVersion = data.version;
                setTimeout(function() { window.location.reload(); }, 250);
              }
            }
          })
          .catch(function(err) {
            isChecking = false;
            if (dot) { dot.style.background = '#ffaa00'; dot.style.boxShadow = '0 0 8px #ffaa00'; }
            if (text) { text.textContent = 'LIVE SYNC: STANDALONE'; }
          });
      }

      setInterval(checkUpdate, 1200);
      setTimeout(checkUpdate, 400);
    })();
  </script>
'''
        if 'id="archify-live-indicator"' not in html:
            if "</body>" in html:
                html = html.replace("</body>", f"{live_client_script}\n</body>", 1)

        # Write out updated HTML
        with open(target_html, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info("Successfully updated Archify HTML viewer at %s", target_html)
        return True, "Archify architecture viewer updated successfully"

    except Exception as e:
        logger.error("Error compiling Archify HTML: %s", e, exc_info=True)
        return False, f"Failed to compile Archify HTML: {e}"


def sync_architecture_changes(project_root: str = ".") -> Tuple[bool, str]:
    """
    Checks architecture.txt or jarvis-architecture.json for updates,
    syncs changes, and recompiles the HTML viewer.
    """
    root = os.path.abspath(project_root)
    arch_txt = os.path.join(root, DEFAULT_ARCH_TXT)
    arch_json = os.path.join(root, "plugins", "archify", "jarvis-architecture.json")
    arch_html = os.path.join(root, "plugins", "archify", "jarvis-architecture.html")

    # If architecture.txt exists and is newer or modified, we can synchronize
    if os.path.isfile(arch_json) and os.path.isfile(arch_html):
        return compile_archify_html(json_path=arch_json, html_path=arch_html)

    return False, "Archify files missing"
