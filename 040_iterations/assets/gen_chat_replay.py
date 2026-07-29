#!/usr/bin/env python3
"""Render a premium dark-mode chat-replay GIF from real tested transcripts.

No live cluster needed — this faithfully re-creates the tested conversations
(Inference Steward iter-1 read-only and iter-2 gated-write) as a looping,
LinkedIn-ready animation. Pillow-only (no ffmpeg).
"""
import glob
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 620
BG = (13, 17, 23)          # #0d1117
HEADER = (22, 27, 34)      # #161b22
USER = (31, 111, 235)      # blue #1f6feb
BOT = (33, 38, 45)         # #21262d
BOT_ACCENT = (46, 160, 67) # green
TXT = (230, 237, 243)
MUT = (139, 148, 158)
BADGE = (35, 30, 15)
BADGE_TXT = (210, 168, 70)

FD = "/usr/share/fonts/truetype/dejavu"
def _f(name, size):
    p = f"{FD}/{name}"
    if not glob.glob(p):
        p = glob.glob(f"{FD}/DejaVuSans.ttf")[0]
    return ImageFont.truetype(p, size)

F   = _f("DejaVuSans.ttf", 24)
FB  = _f("DejaVuSans-Bold.ttf", 24)
FSB = _f("DejaVuSans-Bold.ttf", 27)
FS  = _f("DejaVuSans.ttf", 19)
FT  = _f("DejaVuSans-Bold.ttf", 21)

PAD_X, MAXW = 26, 640
LINE_H, GAP = 33, 16


def wrap(draw, text, font, maxw):
    out = []
    for para in text.split("\n"):
        words, line = para.split(" "), ""
        for w in words:
            t = (line + " " + w).strip()
            if draw.textlength(t, font=font) <= maxw:
                line = t
            else:
                if line:
                    out.append(line)
                line = w
        out.append(line)
    return out


def bubble_size(draw, lines, font):
    tw = max((draw.textlength(l, font=font) for l in lines), default=0)
    return int(tw) + 2 * PAD_X, len(lines) * LINE_H + 2 * 14


def rr(draw, box, r, fill):
    draw.rounded_rectangle(box, radius=r, fill=fill)


def render(messages, typing=False, header="Inference Steward"):
    """messages: list of dicts {role:user|bot|badge, text, accent?}"""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # layout bubbles bottom-anchored (oldest scroll off the top, newest always visible)
    items = []
    for m in messages:
        font = F
        lines = wrap(d, m["text"], font, MAXW)
        bw, bh = bubble_size(d, lines, font)
        items.append((m, lines, bw, bh))
    if typing:
        items.append(({"role": "bot", "typing": True}, ["● ● ●"], 110, 56))

    total = sum(bh + GAP for *_, bh in items)
    y = H - 24 - total  # may be negative → top messages scroll under the header
    for m, lines, bw, bh in items:
        role = m["role"]
        if role == "user":
            x0 = W - 24 - bw
            rr(d, [x0, y, x0 + bw, y + bh], 18, USER)
            fill = (255, 255, 255)
            for i, l in enumerate(lines):
                d.text((x0 + PAD_X, y + 14 + i * LINE_H), l, font=F, fill=fill)
        elif role == "badge":
            x0 = (W - bw) // 2
            rr(d, [x0, y, x0 + bw, y + bh], 14, BADGE)
            for i, l in enumerate(lines):
                d.text((x0 + PAD_X, y + 14 + i * LINE_H), l, font=FS, fill=BADGE_TXT)
        else:
            x0 = 24
            col = BOT
            rr(d, [x0, y, x0 + bw, y + bh], 18, col)
            acc = m.get("accent")
            if acc:
                d.rounded_rectangle([x0, y, x0 + 6, y + bh], radius=3, fill=acc)
            if m.get("typing"):
                d.text((x0 + PAD_X, y + 12), "typing", font=FS, fill=MUT)
                d.text((x0 + PAD_X + 78, y + 8), "●●●", font=FT, fill=MUT)
            else:
                for i, l in enumerate(lines):
                    d.text((x0 + PAD_X, y + 14 + i * LINE_H), l, font=F, fill=TXT)
        y += bh + GAP

    # header bar drawn LAST so scrolled-off messages are masked cleanly
    d.rectangle([0, 0, W, 60], fill=HEADER)
    d.ellipse([24, 24, 38, 38], fill=BOT_ACCENT)
    d.text((50, 16), header, font=FT, fill=TXT)
    d.text((W - 250, 20), "MeshOps  ·  live replay", font=FS, fill=MUT)
    return img


def build(convo, header, outfile, endcard):
    frames, durs = [], []
    shown = []
    for m in convo:
        if m["role"] == "bot":
            frames.append(render(shown, typing=True, header=header)); durs.append(650)
        shown = shown + [m]
        frames.append(render(shown, header=header))
        durs.append(1500 if m["role"] != "badge" else 1100)
    # end card
    ec = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(ec)
    d.rectangle([0, H//2 - 90, W, H//2 + 90], fill=HEADER)
    l1, l2, l3 = endcard
    d.text(((W - d.textlength(l1, font=FSB)) // 2, H//2 - 74), l1, font=FSB, fill=TXT)
    d.text(((W - d.textlength(l2, font=FB)) // 2, H//2 - 28), l2, font=FB, fill=BOT_ACCENT)
    d.text(((W - d.textlength(l3, font=FS)) // 2, H//2 + 28), l3, font=FS, fill=MUT)
    frames.append(ec); durs.append(2600)
    # hold last convo a touch by re-appending first frame at end for clean loop
    frames[0].save(outfile, save_all=True, append_images=frames[1:],
                   duration=durs, loop=0, optimize=True, disposal=2)
    print(f"wrote {outfile} ({len(frames)} frames)")


# ---- Iteration 1: read-only (real tested Q&A) ----
convo1 = [
    {"role": "user", "text": "What engine and preset is serving the model, and the max context?"},
    {"role": "bot",  "text": "phi-4-mini-instruct on Standard_NC4as_T4_v3 (NVIDIA T4).\nMax context 128k tokens.  Workspace: lab-phi-4-mini-eus2-01."},
    {"role": "user", "text": "Is the model healthy right now?"},
    {"role": "bot",  "text": "Yes — State: Ready.  ResourceReady ✓  InferenceReady ✓\n1/1 replica ready in meshops-workloads.", "accent": BOT_ACCENT},
    {"role": "user", "text": "Scale the model to 2 replicas."},
    {"role": "bot",  "text": "I can't do that. I'm read-only — I observe and report,\nI don't change the cluster.", "accent": (210, 90, 70)},
]
build(convo1, "Inference Steward — read-only (iteration 1)",
      "iter1.gif",
      ("MeshOps — Inference Steward · Iteration 1",
       "Stewards propose. Humans dispose.",
       "Read-only, enforced 3 ways · grounded in live cluster state"))

# ---- Iteration 2: gated write + HITL (real tested outcomes) ----
convo2 = [
    {"role": "user", "text": "Create a diagnostic pod."},
    {"role": "bot",  "text": "Proposal pw_4359344e — create Pod in meshops-workloads.\nDry-run OK. Review & merge the PR to approve."},
    {"role": "badge", "text": "GitHub PR merged by ramanjk  →  approved"},
    {"role": "bot",  "text": "Executed ✓  pod created.  Approver: ramanjk.", "accent": BOT_ACCENT},
    {"role": "user", "text": "Scale the workspace to 2 replicas."},
    {"role": "bot",  "text": "Denied at the gate — KAITO: resource.count is immutable.\nFails closed even if approved.", "accent": (210, 90, 70)},
]
build(convo2, "Inference Steward — gated write + HITL (iteration 2)",
      "iter2.gif",
      ("MeshOps — Inference Steward · Iteration 2",
       "Stewards propose. Humans dispose. — with teeth.",
       "Approve · Reject · Fail-closed  ·  every action audited"))
