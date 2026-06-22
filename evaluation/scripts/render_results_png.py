#!/usr/bin/env python3
"""Render the complete 67-Q results (joint benchmark + isolated-grader experiments) to a PNG."""
from PIL import Image, ImageDraw, ImageFont

FD = "/usr/share/fonts/truetype/dejavu/"
def font(name, size):
    return ImageFont.truetype(FD + name, size)
F_TITLE   = font("DejaVuSans-Bold.ttf", 32)
F_SECTION = font("DejaVuSans-Bold.ttf", 22)
F_SUB     = font("DejaVuSans-Bold.ttf", 17)
F_HEAD    = font("DejaVuSans-Bold.ttf", 15)
F_CELL    = font("DejaVuSans.ttf", 15)
F_CAP     = font("DejaVuSans.ttf", 14)

INK = (28, 32, 38)
MUTE = (95, 102, 112)
HEAD_BG = (38, 44, 54)
HEAD_FG = (255, 255, 255)
ROW_A = (255, 255, 255)
ROW_B = (244, 246, 249)
GRID = (210, 215, 222)
GREEN = (22, 130, 70)
RED = (193, 39, 45)
BAND = (200, 16, 46)         # brand-ish accent for section bars

W = 1560
M = 44
draw_imgs = []

# ---- data -------------------------------------------------------------------
joint_headers = ["Run / arm", "Change", "n", "Mean", "Δ base", "A/B/C/D", "Notes"]
joint_fracs   = [0.20, 0.20, 0.045, 0.07, 0.075, 0.10, 0.305]
joint_rows = [
    ["baseline-…134705", "baseline", "66", "77.74", "—", "0/38/22/6", "1 not-gradable"],
    ["post-improvement-…182930", "C5 empty-answer guard", "66", "79.36", "+1.62", "0/44/19/3", "within run-to-run noise"],
    ["youmans-full67 · recent", "3-arm A/B (recent)", "67", "78.66", "+0.92", "0/44/22/0", "length confound on composed arm"],
    ["youmans-full67 · youmans", "3-arm A/B (youmans)", "67", "80.03", "+2.29", "0/55/11/0", "length confound on composed arm"],
    ["youmans-full67 · youmans_pubmed", "3-arm A/B (youmans_pubmed)", "67", "83.87", "+6.13", "0/61/5/0", "length confound on composed arm"],
]
joint_delta = {4}

b_headers = ["Arm", "n", "Mean", "Δ vs core", "Read"]
b_fracs   = [0.30, 0.05, 0.08, 0.10, 0.47]
b_rows = [
    ["core  (youmans, no appendix)", "64", "86.16", "—", "control"],
    ["real  (+ real PubMed appendix)", "64", "86.11", "−0.05", "appendix is score-neutral → the +3.9 was a joint-grading artifact"],
    ["placebo  (+ length-matched boilerplate)", "64", "80.59", "−5.56", "padding hurts → NOT a length effect"],
    ["scramble  (+ wrong-topic real appendix)", "64", "61.25", "−24.91", "off-topic content is catastrophic → relevance gating matters"],
]
b_delta = {3}

m_headers = ["Run", "n", "Mean off", "Mean on", "Δ (on−off)", "95% CI", "W/L/T"]
m_fracs   = [0.20, 0.06, 0.13, 0.13, 0.14, 0.20, 0.14]
m_rows = [
    ["MMR on @0.07", "62", "83.56", "84.81", "+1.24", "[−1.21, +3.69]", "26/26/10"],
    ["MMR on @0.15", "59", "85.61", "85.80", "+0.19", "[−2.48, +2.85]", "18/23/18"],
]
m_delta = {4}

s_headers = ["Subspecialty", "Δ @0.07", "Δ @0.15"]
s_fracs   = [0.5, 0.25, 0.25]
s_rows = [
    ["Neurointerventional", "+9.9", "+8.9"],
    ["Spine", "+4.4", "−3.3"],
    ["Brain Tumor", "+3.1", "+4.9"],
    ["Open Cerebrovascular", "+1.2", "+1.0"],
    ["General", "−1.1", "+0.9"],
    ["Functional", "−2.6", "−5.3"],
    ["Trauma", "−3.9", "−4.8"],
    ["Overall", "+1.24", "+0.19"],
]
s_delta = {1, 2}

# ---- helpers ----------------------------------------------------------------
_md = ImageDraw.Draw(Image.new("RGB", (10, 10)))
def tw(s, f):
    return _md.textlength(s, font=f)

def wrap(text, f, maxw):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if tw(t, f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines or [""]

def delta_color(s):
    s = s.strip()
    if s.startswith("+"): return GREEN
    if s.startswith("−") or s.startswith("-"): return RED
    return INK

def measure_table(headers, fracs, rows, delta):
    cols = [int(f * (W - 2 * M)) for f in fracs]
    pad = 10
    lh = 21
    head_h = 34
    row_heights = []
    wrapped = []
    for r in rows:
        wr = []
        for ci, cell in enumerate(r):
            wr.append(wrap(cell, F_CELL, cols[ci] - 2 * pad))
        wrapped.append(wr)
        row_heights.append(max(len(x) for x in wr) * lh + 12)
    return cols, pad, lh, head_h, row_heights, wrapped, sum(row_heights) + head_h

def draw_table(d, x, y, headers, fracs, rows, delta):
    cols, pad, lh, head_h, row_heights, wrapped, total = measure_table(headers, fracs, rows, delta)
    tot_w = sum(cols)
    # header
    d.rectangle([x, y, x + tot_w, y + head_h], fill=HEAD_BG)
    cx = x
    for ci, h in enumerate(headers):
        d.text((cx + pad, y + 8), h, font=F_HEAD, fill=HEAD_FG)
        cx += cols[ci]
    yy = y + head_h
    for ri, r in enumerate(rows):
        rh = row_heights[ri]
        bg = ROW_B if ri % 2 else ROW_A
        if rows is s_rows and r[0] == "Overall":
            bg = (232, 236, 242)
        d.rectangle([x, yy, x + tot_w, yy + rh], fill=bg)
        cx = x
        for ci, cell in enumerate(r):
            color = delta_color(cell) if ci in delta else INK
            f = F_HEAD if (rows is s_rows and r[0] == "Overall") else F_CELL
            for li, ln in enumerate(wrapped[ri][ci]):
                d.text((cx + pad, yy + 6 + li * lh), ln, font=f, fill=color)
            cx += cols[ci]
        d.line([x, yy, x + tot_w, yy], fill=GRID)
        yy += rh
    # outer + column grid
    d.rectangle([x, y, x + tot_w, yy], outline=GRID)
    cx = x
    for ci in range(len(cols) - 1):
        cx += cols[ci]
        d.line([cx, y, cx, yy], fill=GRID)
    return yy

# ---- layout pass: compute height --------------------------------------------
def section_bar_h(): return 40
def sub_h(): return 30

blocks = []  # (kind, payload)
blocks.append(("title", "Neuro·Caseboard — 67-Question Benchmark: All Run Results"))
blocks.append(("section", "Joint-graded benchmark  ·  3-arm A/B + baseline runs (mean = 0–100, Δ vs baseline)"))
blocks.append(("table", (joint_headers, joint_fracs, joint_rows, joint_delta)))
blocks.append(("section", "Isolated-grader experiments  ·  different grader — read the paired Δ vs control, NOT the absolute mean"))
blocks.append(("sub", "Phase 0B — PubMed lane de-confound  (isolated grading, n=64; control = core)"))
blocks.append(("table", (b_headers, b_fracs, b_rows, b_delta)))
blocks.append(("sub", "Phase 1-D — MMR diversity score effect  (isolated grading, paired off vs on)"))
blocks.append(("table", (m_headers, m_fracs, m_rows, m_delta)))
blocks.append(("sub", "Phase 1-D — MMR Δ (on−off) by subspecialty"))
blocks.append(("table", (s_headers, s_fracs, s_rows, s_delta)))
caption = ("Takeaway: the +3.9 “PubMed gain” is a joint-grading artifact (real appendix is score-neutral in isolation, −0.05); "
           "MMR helps the specialized fields Youmans crowds out (NIS +9.9, Tumor +3.1, Spine +4.4 @0.07) but a flat global penalty is only "
           "mildly net-positive. Recommend default RERANK_MMR_BOOK_PENALTY=0.0; 0.07 if enabling; subspecialty-conditional is the real fix. "
           "Single self-grader (gemini-2.5-pro), n≈60 — directional.")
blocks.append(("caption", caption))

y = M
heights = []
for kind, payload in blocks:
    if kind == "title": y += 46
    elif kind == "section": y += section_bar_h() + 8
    elif kind == "sub": y += sub_h()
    elif kind == "table":
        _, _, _, _, _, _, th = measure_table(*payload)
        y += th + 18
    elif kind == "caption":
        lines = wrap(payload, F_CAP, W - 2 * M)
        y += len(lines) * 20 + 12
H = y + M

# ---- draw pass --------------------------------------------------------------
img = Image.new("RGB", (W, H), (255, 255, 255))
d = ImageDraw.Draw(img)
y = M
for kind, payload in blocks:
    if kind == "title":
        d.text((M, y), payload, font=F_TITLE, fill=INK)
        y += 46
    elif kind == "section":
        d.rectangle([M, y, M + 6, y + section_bar_h() - 8], fill=BAND)
        d.text((M + 16, y + 4), payload, font=F_SECTION, fill=INK)
        y += section_bar_h() + 8
    elif kind == "sub":
        d.text((M, y + 4), payload, font=F_SUB, fill=(60, 66, 76))
        y += sub_h()
    elif kind == "table":
        y = draw_table(d, M, y, *payload) + 18
    elif kind == "caption":
        for ln in wrap(payload, F_CAP, W - 2 * M):
            d.text((M, y), ln, font=F_CAP, fill=MUTE)
            y += 20

out = "/home/michael/PROJECTS/neuro-caseboard/eval/results_table.png"
img.save(out)
print("wrote", out, img.size)
