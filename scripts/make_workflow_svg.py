"""Generate docs/assets/agentic-workflow.svg: an animated, 3D-style map of one curation run.

The SVG uses only SMIL + CSS animation (no script), so GitHub renders and animates it
inside a README. Run:  python scripts/make_workflow_svg.py
"""
from __future__ import annotations

from pathlib import Path

W, H = 1600, 1000
DX, DY = 16, -12          # 3D depth offset for box tops/sides
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "agentic-workflow.svg"

PALETTE = {
    "you": ("#f7b267", "#d98b3a", "#b56d24"),
    "cli": ("#9aa8c7", "#7584a6", "#5b6987"),
    "orch": ("#7aa2ff", "#4f7ae6", "#3a5fc0"),
    "bus": ("#6fd3c4", "#45b3a3", "#33907f"),
    "board": ("#c3a6ff", "#9c7ae6", "#7d5ac4"),
    "safe": ("#ff9f9f", "#e66f6f", "#c15050"),
    "agent": ("#8fe0a4", "#5cc47a", "#3f9e5c"),
    "mcpc": ("#ffd36e", "#e6b445", "#c29230"),
    "mcps": ("#ffb36e", "#e68d45", "#c06d2c"),
    "llm": ("#f5a3d8", "#de76bd", "#b9579b"),
    "lib": ("#9fd1ff", "#6eb2f0", "#4f90cc"),
}

parts: list[str] = []
add = parts.append


def box(x, y, w, h, key, title, sub="", rx=10, tsize=17):
    top, front, side = PALETTE[key]
    add(f'<g class="box">')
    add(f'<polygon points="{x},{y} {x+DX},{y+DY} {x+w+DX},{y+DY} {x+w},{y}" fill="{top}"/>')
    add(f'<polygon points="{x+w},{y} {x+w+DX},{y+DY} {x+w+DX},{y+h+DY} {x+w},{y+h}" fill="{side}"/>')
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{front}" filter="url(#soft)"/>')
    ty = y + (h / 2 if not sub else h / 2 - 8)
    add(f'<text x="{x+w/2}" y="{ty+6}" class="t" font-size="{tsize}">{title}</text>')
    if sub:
        add(f'<text x="{x+w/2}" y="{ty+26}" class="s">{sub}</text>')
    add("</g>")


def cylinder(x, y, w, h, key, title, sub):
    top, front, side = PALETTE[key]
    ry = 16
    add(f'<path d="M{x},{y} v{h} a{w/2},{ry} 0 0 0 {w},0 v{-h}" fill="{front}" filter="url(#soft)"/>')
    add(f'<ellipse cx="{x+w/2}" cy="{y}" rx="{w/2}" ry="{ry}" fill="{top}"/>')
    add(f'<text x="{x+w/2}" y="{y+h/2+4}" class="t" font-size="17">{title}</text>')
    add(f'<text x="{x+w/2}" y="{y+h/2+24}" class="s">{sub}</text>')


def flow(pid, d, color, dur, begin, label=None, lx=0, ly=0, dashed=False, r=6):
    """A path drawn as a moving dashed line, with a glowing packet travelling along it."""
    cls = "flow dash" if dashed else "flow"
    add(f'<path id="{pid}" d="{d}" class="{cls}" stroke="{color}" marker-end="url(#arr)"/>')
    add(f'<circle r="{r}" fill="{color}" filter="url(#glow)" opacity="0">'
        f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.1;0.85;1" dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/>'
        f'<animateMotion dur="{dur}s" begin="{begin}s" repeatCount="indefinite" rotate="auto">'
        f'<mpath href="#{pid}"/></animateMotion></circle>')
    if label:
        add(f'<text x="{lx}" y="{ly}" class="lbl">{label}</text>')


def step(n, x, y, text):
    add(f'<g><circle cx="{x}" cy="{y}" r="13" fill="#ffffff"/>'
        f'<text x="{x}" y="{y+5}" class="num">{n}</text>'
        f'<text x="{x+20}" y="{y+5}" class="step">{text}</text></g>')


# ---------- header ----------
add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
    f'font-family="Segoe UI, Helvetica, Arial, sans-serif">')
add("""<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0f1729"/><stop offset="1" stop-color="#1c2a48"/></linearGradient>
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#ffffff" stroke-opacity="0.04"/></pattern>
<filter id="soft" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#000" flood-opacity="0.45"/></filter>
<filter id="glow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#dfe6f5"/></marker>
</defs>
<style>
.t{fill:#0d1424;font-weight:700;text-anchor:middle}
.s{fill:#0d1424;font-size:12.5px;text-anchor:middle;opacity:.85}
.lbl{fill:#cfd8ea;font-size:13px;font-style:italic}
.flow{fill:none;stroke-width:2.6;stroke-dasharray:9 7;animation:run 1.2s linear infinite;opacity:.85}
.dash{stroke-dasharray:4 6}
@keyframes run{to{stroke-dashoffset:-32}}
.num{fill:#0f1729;font-size:13px;font-weight:800;text-anchor:middle}
.step{fill:#e6ecf8;font-size:14px}
.h1{fill:#ffffff;font-size:30px;font-weight:800}
.h2{fill:#9fb0d0;font-size:15px}
.zone{fill:#ffffff;fill-opacity:.035;stroke:#ffffff;stroke-opacity:.12;stroke-dasharray:6 6}
.zl{fill:#8fa3c8;font-size:13px;font-weight:700;letter-spacing:2px}
.pulse{animation:pulse 2.4s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
@keyframes pulse{0%,100%{opacity:.55}50%{opacity:1}}
</style>""")
add(f'<rect width="{W}" height="{H}" fill="url(#bg)"/><rect width="{W}" height="{H}" fill="url(#grid)"/>')
add('<text x="40" y="52" class="h1">Agentic Curator · how one run flows</text>')
add('<text x="40" y="78" class="h2">Orchestrator plans · subagents work in parallel · every file touch goes through MCP · nothing is deleted without your approval</text>')

# ---------- zones ----------
add('<rect x="22" y="300" width="300" height="440" rx="18" class="zone"/><text x="40" y="326" class="zl">CLIENT</text>')
add('<rect x="430" y="104" width="1150" height="520" rx="18" class="zone"/><text x="448" y="130" class="zl">AGENT LAYER</text>')
add('<rect x="430" y="640" width="1150" height="340" rx="18" class="zone"/><text x="448" y="666" class="zl">MCP LAYER</text>')

# ---------- the client: person at a desk with a photo library ----------
add('<g transform="translate(70,370)">')
add('<rect x="-10" y="200" width="230" height="16" rx="4" fill="#3a4a6b"/>')                 # desk
add('<rect x="40" y="128" width="130" height="78" rx="6" fill="#26324d" stroke="#7aa2ff" stroke-width="2"/>')  # laptop screen
add('<rect x="22" y="204" width="166" height="8" rx="3" fill="#56688f"/>')
add('<text x="105" y="160" fill="#9fd1ff" font-size="12" text-anchor="middle" font-family="Consolas,monospace">$ curator run</text>')
add('<text x="105" y="180" fill="#8fe0a4" font-size="12" text-anchor="middle" font-family="Consolas,monospace" class="pulse">dry-run ✓</text>')
add('<circle cx="105" cy="34" r="30" fill="#f7b267"/>')                                         # head
add('<path d="M45,128 q0,-58 60,-58 q60,0 60,58 z" fill="#d98b3a"/>')                          # shoulders
# floating photo icon
add('<g class="pulse"><rect x="168" y="-2" width="62" height="50" rx="7" fill="#ffffff"/>'
    '<rect x="174" y="4" width="50" height="34" rx="3" fill="#6eb2f0"/>'
    '<circle cx="212" cy="13" r="5" fill="#ffd36e"/>'
    '<path d="M174,38 l16,-18 l12,12 l8,-8 l14,14 z" fill="#3f9e5c"/></g>')
add('<text x="105" y="250" fill="#ffffff" font-size="18" font-weight="700" text-anchor="middle">You</text>')
add('<text x="105" y="270" fill="#9fb0d0" font-size="13" text-anchor="middle">photos · docs · Takeout</text>')
add("</g>")

# ---------- agent layer ----------
box(500, 160, 320, 74, "orch", "Orchestrator", "plans phases · owns no files")
box(1000, 150, 250, 66, "llm", "LLM provider", "Anthropic · Gemini · OpenAI · offline")
box(1300, 150, 240, 66, "board", "Blackboard", "facts · proposals · evidence")
box(500, 300, 320, 60, "bus", "Agent Bus", "routes tasks · parallel fan-out")
box(1300, 290, 240, 76, "safe", "Safety Policy", "dry-run · confidence ≥ 0.90")

agents = [("Year", "group by year"), ("Document", "read · classify"), ("Duplicate", "sha256 · Jaccard"),
          ("Photo", "dHash · bursts"), ("Consolidator", "merge notes"), ("Deletion", "trash on approval")]
ax0, aw, gap, ay = 470, 160, 22, 450
centers = []
for i, (name, sub) in enumerate(agents):
    x = ax0 + i * (aw + gap)
    box(x, ay, aw, 66, "agent", f"{name} agent", sub, tsize=15)
    centers.append(x + aw / 2)

# ---------- MCP layer ----------
box(470, 700, 1072, 56, "mcpc", "MCP Client  ·  ClientSession", "one session per run · tools discovered at start")
box(470, 860, 700, 70, "mcps", "MCP Server  ·  library_server", "sandboxed to your library folder")
tools = ["list_items", "read_text", "hash_item", "image_signature", "write_text", "move_to_trash"]
for i, t in enumerate(tools):
    tx = 476 + i * 116
    add(f'<rect x="{tx}" y="940" width="112" height="26" rx="13" fill="#2b3a5c" stroke="#e68d45"/>'
        f'<text x="{tx+56}" y="957" fill="#ffd9b8" font-size="11" text-anchor="middle" font-family="Consolas,monospace">{t}</text>')
cylinder(1250, 860, 290, 80, "lib", "Your library", "photos · docs · trash manifest")

# ---------- flows (numbered to match the steps) ----------
flow("f1", "M240,520 C300,520 330,240 492,205", "#f7b267", 3.0, 0, "curator run", 280, 262)
flow("f2", "M660,240 L660,292", "#7aa2ff", 1.6, 0.6)
for i, cx in enumerate(centers):
    flow(f"f3{i}", f"M660,366 C660,410 {cx},400 {cx},442", "#6fd3c4", 2.0, 1.0 + i * 0.15)
for i, cx in enumerate(centers):
    flow(f"f4{i}", f"M{cx},522 L{cx},692", "#8fe0a4", 1.8, 2.0 + i * 0.12)
flow("f5", "M820,762 L820,852", "#ffd36e", 1.4, 3.0, "stdio · JSON-RPC", 832, 812)
flow("f5b", "M760,852 L760,762", "#ffb36e", 1.4, 3.6, "results", 650, 812, dashed=True)
flow("f6", "M1172,895 L1242,895", "#9fd1ff", 1.2, 3.3)
for i, cx in enumerate(centers):
    flow(f"f7{i}", f"M{cx},442 L{cx},424 L1576,424 L1576,186 L1560,186", "#c3a6ff", 3.0, 4.2 + i * 0.2, dashed=True)
add('<text x="1418" y="414" class="lbl">findings + proposals</text>')
flow("f8", "M822,190 L992,184", "#f5a3d8", 1.5, 5.0, "second opinion", 848, 176)
flow("f9", "M1420,226 L1420,282", "#c3a6ff", 1.2, 5.5)
flow("f10", "M1300,330 C1280,330 1270,392 1240,392 L462,392 C448,392 448,402 448,412 L448,584 C448,594 442,598 432,598 L300,598 C272,598 262,590 252,580", "#ff9f9f", 3.6, 6.0, "plan.json + report → you approve", 520, 590)
flow("f11", f"M{centers[5]},522 C{centers[5]},600 1420,640 1420,852", "#ff6f6f", 2.4, 7.2, "approved → move_to_trash", 1290, 640, dashed=True)

# ---------- step legend ----------
steps = ["You start a run (dry-run by default)", "Orchestrator splits the job into phases",
         "Bus fans tasks out to six subagents", "Subagents act only through MCP tools",
         "Server reads, hashes and fingerprints files", "Findings land on the Blackboard",
         "Safety Policy builds a plan you approve", "Deletion agent trashes – reversible"]
lx, ly = 40, 770
add(f'<rect x="{lx-14}" y="{ly-28}" width="390" height="226" rx="14" fill="#0b1222" fill-opacity=".75" stroke="#ffffff" stroke-opacity=".12"/>')
for i, s in enumerate(steps):
    step(i + 1, lx + 6, ly + i * 26 + 0, s)

add("</svg>")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(p for p in parts if p), encoding="utf-8")
print("wrote", OUT, OUT.stat().st_size, "bytes")
