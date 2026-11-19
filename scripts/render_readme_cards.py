#!/usr/bin/env python3
"""
Render the profile README's cards as animated SVGs into cards/.

Theme: deep space — ink-dark cards, one accent per world (AI cyan, GAME amber,
SPACE violet), Instrument Serif display type, Space Grotesk UI, JetBrains Mono
labels.

Every card is a standalone SVG shown through <img>, so it can only use what
GitHub allows there: inline CSS animations, SMIL, and fonts embedded as data
URIs (no JS, no external requests).

Spacing between cards is baked into each SVG canvas (see svg(left=, right=)), so
a row of three tiles exactly 33.333% wide has even 12px gaps. Keep the README
block free of blank lines and put the cards on one line with no spaces between
them.

Live numbers come from data/contributions.json (fetch_contributions.py); the
portrait comes from assets/ascii.json (make_ascii_svg.py).

STATIC=1 renders every animation at its end state for screenshots.
"""

import base64
import datetime
import json
import os
import re
from html import escape
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data", "contributions.json")
ASCII = os.path.join(ROOT, "assets", "ascii.json")
OUT = os.path.join(ROOT, "cards")
FONTS = os.path.join(ROOT, "fonts")

USERNAME = "palturuvenubhaskar"
STATIC = bool(os.environ.get("STATIC"))

# ---- palette ----------------------------------------------------------------
BG = "#070a10"
CARD = "#0c111a"
CARD_DEEP = "#0a0f17"
INK = "#e8eef8"
INK_SOFT = "#c2cbd9"
MUTED = "#8b97ab"
FAINT = "#5a6678"
RULE = "#1b2434"
TECH = "#22d3ee"      # AI orchestration
STUDIO = "#fb923c"    # game dev
LEARN = "#a78bfa"     # space tech
W = 880               # full card width, GitHub's README column at 100%

SERIF = "'Instrument Serif', Georgia, serif"
SANS = "'Space Grotesk', system-ui, -apple-system, sans-serif"
MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

FONT_FILES = {
    "serif": ("Instrument Serif", "normal", 400, "is400"),
    "serif-i": ("Instrument Serif", "italic", 400, "is400i"),
    "sans": ("Space Grotesk", "normal", 500, "sg500"),
    "sans-b": ("Space Grotesk", "normal", 700, "sg700"),
    "mono": ("JetBrains Mono", "normal", 400, "jbm400"),
}

BASE_CSS = """
@keyframes rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes pop{0%{opacity:0;transform:scale(.3)}70%{opacity:1;transform:scale(1.15)}100%{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@keyframes nudge{0%,100%{transform:none}50%{transform:translateX(4px)}}
@keyframes nudgeup{0%,100%{transform:none}50%{transform:translate(3px,-3px)}}
@keyframes twinkle{0%,100%{opacity:.12}50%{opacity:.55}}
@keyframes tilein{0%{opacity:0;transform:translateY(90px) scale(.6) rotate(-9deg)}55%{opacity:1;transform:translateY(-10px) scale(1.05) rotate(2deg)}75%{transform:translateY(3px) scale(.98) rotate(-.8deg)}90%{transform:translateY(-1px) scale(1.01) rotate(.2deg)}100%{opacity:1;transform:none}}
@keyframes slidein{from{opacity:0;transform:translateX(-26px)}to{opacity:1;transform:none}}
@keyframes arrowin{0%{opacity:0;transform:translateX(-30px)}60%{opacity:1;transform:translateX(6px)}100%{opacity:1;transform:none}}
@keyframes roll{from{transform:translateY(60px)}to{transform:none}}
@keyframes sheen{0%{transform:translateX(-260px) skewX(-20deg)}22%,100%{transform:translateX(420px) skewX(-20deg)}}
@keyframes ring{0%{opacity:.7;transform:scale(.2)}100%{opacity:0;transform:scale(2.4)}}
.r{opacity:0;animation:rise .8s cubic-bezier(.2,.7,.2,1) both;transform-box:fill-box}
.f{opacity:0;animation:fade .9s ease-out both}
.g{transform-box:fill-box;transform-origin:bottom;transform:scaleY(0);animation:grow .8s cubic-bezier(.2,.7,.2,1) both}
.p{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .4s ease-out both}
.live{animation:pulse 1.6s ease-in-out infinite}
.n{transform-box:fill-box;animation:nudge 1.8s ease-in-out infinite}
.nu{transform-box:fill-box;animation:nudgeup 1.8s ease-in-out infinite}
.tw{animation:twinkle 4s ease-in-out infinite}
.ti{opacity:0;transform-box:fill-box;transform-origin:50% 60%;animation:tilein 1.1s cubic-bezier(.2,.8,.2,1) both}
.sl{opacity:0;transform-box:fill-box;animation:slidein .6s cubic-bezier(.2,.7,.2,1) both}
.ai{opacity:0;transform-box:fill-box;animation:arrowin .7s cubic-bezier(.2,.7,.2,1) both}
.ro{transform-box:fill-box;animation:roll .8s cubic-bezier(.15,.8,.2,1) both}
.sh{animation:sheen 5s ease-in-out infinite}
.rg{opacity:0;transform-box:fill-box;transform-origin:center;animation:ring 1s ease-out both}
@media (prefers-reduced-motion: reduce){.r,.f,.g,.p,.live,.n,.nu,.tw,.ti,.sl,.ai,.ro,.rg{animation:none!important;opacity:1!important;transform:none!important}.sh,.rg{display:none}}
"""

STATIC_CSS = (
    ".r,.f,.g,.p,.live,.n,.nu,.tw,.ti,.sl,.ai,.ro{animation:none!important;"
    "opacity:1!important;transform:none!important}.sh,.rg{display:none}"
)

GAP = 12          # gap between cards, baked into the SVGs
BOTTOM = 12       # bottom padding per row, matching GAP
COL = W / 3       # each card in a row of three is exactly a third of the column


def font_face(keys):
    out = []
    for k in keys:
        fam, style, weight, stem = FONT_FILES[k]
        path = None
        for cand in (f"sub-{stem}.woff2", f"{stem}.woff2"):
            p = os.path.join(FONTS, cand)
            if os.path.exists(p):
                path = p
                break
        if not path:
            print(f"[warn] font missing: {stem}")
            continue
        b64 = base64.b64encode(open(path, "rb").read()).decode()
        out.append(
            f"@font-face{{font-family:'{fam}';font-style:{style};font-weight:{weight};"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');font-display:block}}"
        )
    return "".join(out)


def svg(w, h, body, fonts, label, extra_css="", left=0, right=0, bottom=BOTTOM):
    """Card of w x h drawn at x=left on a transparent canvas, padded so rows tile exactly."""
    if left:
        body = f'<g transform="translate({left:.3f} 0)">{body}</g>'
    w, h = w + left + right, h + bottom
    css = font_face(fonts) + BASE_CSS + extra_css
    if STATIC:
        css += STATIC_CSS
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.3f}" height="{h}" '
        f'viewBox="0 0 {w:.3f} {h}" role="img" aria-label="{escape(label)}">'
        f"<title>{escape(label)}</title><style>{css}</style>{body}</svg>"
    )


def write(name, content):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  wrote cards/{name} ({len(content) // 1024} KB)")


def d(s):
    return f'style="animation-delay:{s:.2f}s"'


def wrap(text, n):
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > n:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + [line] if line else lines


def text_lines(x, y, lines, lh, attrs):
    return "".join(
        f'<text x="{x}" y="{y + i * lh}" {attrs}>{escape(l)}</text>' for i, l in enumerate(lines)
    )


def stars():
    """A few faint stars for the space theme (deterministic positions)."""
    pts = [
        (500, 26), (560, 120), (620, 40), (700, 200), (770, 110), (840, 70),
        (840, 250), (520, 300), (590, 350), (700, 330), (800, 360), (660, 300),
        (480, 190), (500, 380), (846, 196), (724, 386),
    ]
    out = []
    for i, (x, y) in enumerate(pts):
        r = 1.0 if i % 3 else 1.4
        out.append(
            f'<circle class="tw" style="animation-delay:{i * 0.31:.2f}s" cx="{x}" cy="{y}" '
            f'r="{r}" fill="{INK}" opacity=".18"/>'
        )
    return "".join(out)


# ---- 1 · hero -----------------------------------------------------------------
def hero(contrib):
    h = 400
    art = json.load(open(ASCII, encoding="utf-8"))
    rows = art["lines"]
    art_w, cell_h = art["art_w"], art["cell_h"]
    scale = 0.40
    art_top = 56
    art_x = 520

    total = contrib["total_contributions"]
    active = contrib["active_days"]
    best = contrib["best_day"]["count"]
    days = len(contrib["days"])

    portrait = []
    row_dur = 5.6 / max(1, len(rows))
    for i, line in enumerate(rows):
        y = i * cell_h + cell_h * 0.74
        delay = 0.25 + i * row_dur
        text = (
            f'<text xml:space="preserve" x="0" y="{y:.1f}" fill="{INK}" fill-opacity=".85" '
            f'font-size="{cell_h * 0.86:.1f}" textLength="{art_w:.0f}" '
            f'lengthAdjust="spacing">{escape(line)}</text>'
        )
        if STATIC:
            portrait.append(text)
            continue
        portrait.append(
            f'<clipPath id="pr{i}" clipPathUnits="userSpaceOnUse">'
            f'<rect x="0" y="{i * cell_h:.1f}" height="{cell_h:.1f}" width="{art_w:.0f}">'
            f'<animate attributeName="width" from="0" to="{art_w:.0f}" begin="{delay:.3f}s" '
            f'dur="{row_dur:.2f}s" fill="freeze"/></rect></clipPath>'
            f'<g clip-path="url(#pr{i})">{text}</g>'
            f'<rect y="{i * cell_h + 1:.1f}" width="{art_w / len(rows[0]):.2f}" '
            f'height="{cell_h - 2:.1f}" fill="{TECH}" opacity="0">'
            f'<animate attributeName="x" from="0" to="{art_w:.0f}" begin="{delay:.3f}s" '
            f'dur="{row_dur:.2f}s" fill="freeze"/>'
            f'<set attributeName="opacity" to=".55" begin="{delay:.3f}s"/>'
            f'<set attributeName="opacity" to="0" begin="{delay + row_dur:.3f}s"/></rect>'
        )

    stats = [
        (f"{total:,}", "contributions"),
        (f"{active}", f"active days / {days}"),
        (f"{best}", "best single day"),
    ]
    stat_svg = []
    for i, (big, small) in enumerate(stats):
        x = 44 + i * 168
        stat_svg.append(
            f'<g class="r" {d(1.0 + i * 0.12)}>'
            f'<text x="{x}" y="356" font-family="{SANS}" font-weight="700" font-size="23" fill="{INK}">{big}</text>'
            f'<text x="{x}" y="376" font-family="{MONO}" font-size="9.5" letter-spacing=".6" '
            f'fill="{FAINT}">{escape(small.upper())}</text></g>'
        )

    body = f"""
<defs>
  <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="520" y2="0">
    <stop offset="0" stop-color="{INK}"/><stop offset=".42" stop-color="{INK}"/>
    <stop offset=".5" stop-color="{TECH}"/><stop offset=".58" stop-color="{INK}"/>
    <stop offset="1" stop-color="{INK}"/>
    {"<animateTransform attributeName='gradientTransform' type='translate' values='-520 0;520 0;520 0' keyTimes='0;.45;1' dur='7s' begin='1.6s' repeatCount='indefinite'/>" if not STATIC else ""}
  </linearGradient>
  <radialGradient id="glow" cx="50%" cy="0%" r="80%">
    <stop offset="0" stop-color="{TECH}" stop-opacity=".13"/>
    <stop offset="1" stop-color="{TECH}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="pfx" x1="0" y1="0" x2="1" y2="0">
    <stop offset=".80" stop-color="#fff"/><stop offset="1" stop-color="#000"/>
  </linearGradient>
  <linearGradient id="pfy" x1="0" y1="0" x2="0" y2="1">
    <stop offset=".86" stop-color="#fff"/><stop offset="1" stop-color="#000"/>
  </linearGradient>
  <mask id="pfadex" maskUnits="userSpaceOnUse" x="{art_x}" y="{art_top}"
        width="{art_w * scale:.0f}" height="{art_w * scale:.0f}">
    <rect x="{art_x}" y="{art_top}" width="{art_w * scale:.0f}" height="{art_w * scale:.0f}" fill="url(#pfx)"/>
  </mask>
  <mask id="pfadey" maskUnits="userSpaceOnUse" x="{art_x}" y="{art_top}"
        width="{art_w * scale:.0f}" height="{art_w * scale:.0f}">
    <rect x="{art_x}" y="{art_top}" width="{art_w * scale:.0f}" height="{art_w * scale:.0f}" fill="url(#pfy)"/>
  </mask>
</defs>
<rect width="{W}" height="{h}" rx="14" fill="{CARD}"/>
<rect width="{W}" height="{h}" rx="14" fill="url(#glow)"/>
<rect x=".5" y=".5" width="{W - 1}" height="{h - 1}" rx="14" fill="none" stroke="{RULE}"/>
{stars()}
<g class="f" {d(0)}>
  <rect class="live" x="44" y="48" width="8" height="8" rx="2" fill="{TECH}"/>
  <text x="62" y="56" font-family="{MONO}" font-size="11" letter-spacing="2.2" fill="{MUTED}">AI ORCHESTRATOR &#183; AGENTIC DEVELOPER</text>
</g>
<text class="r" {d(0.15)} x="40" y="170" font-family="{SERIF}" font-size="84" letter-spacing="-1.5" fill="{INK}">Palturu</text>
<text class="r" {d(0.3)} x="40" y="246" font-family="{SERIF}" font-style="italic" font-size="84" letter-spacing="-1.5" fill="url(#shine)">Venubhaskar</text>
<g class="r" {d(0.55)}>
  {text_lines(44, 284, ["CSE student building agentic systems, AI games", "and space-tech tools."], 24, f'font-family="{SANS}" font-size="15.5" fill="{INK_SOFT}"')}
</g>
<line x1="44" y1="326" x2="500" y2="326" stroke="{RULE}"/>
{''.join(stat_svg)}
<g mask="url(#pfadex)"><g mask="url(#pfadey)"><g transform="translate({art_x} {art_top}) scale({scale})" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">
  {''.join(portrait)}
</g></g></g>
"""
    write(
        "hero.svg",
        svg(W, h, body, ["serif", "serif-i", "sans", "sans-b", "mono"],
            f"Palturu Venubhaskar. {total:,} contributions, {active} active days."),
    )


# ---- 2 · world tiles ----------------------------------------------------------
TILE_W, TILE_H = W / 3 - 8, 210


def tile(name, label, color, num, word, blurb, delay, pos):
    lines = wrap(blurb, 34)
    blurb_svg = "".join(
        f'<text class="r" {d(delay + 0.75 + i * 0.1)} x="24" y="{152 + i * 20}" '
        f'font-family="{SANS}" font-size="13.5" fill="{INK_SOFT}">{escape(l)}</text>'
        for i, l in enumerate(lines)
    )
    body = f"""
<defs>
  <clipPath id="card{pos}"><rect width="{TILE_W:.3f}" height="{TILE_H}" rx="14"/></clipPath>
  <clipPath id="slot{pos}"><rect x="0" y="58" width="{TILE_W:.3f}" height="66"/></clipPath>
  <linearGradient id="gl{pos}" x1="0" x2="1">
    <stop offset="0" stop-color="#fff" stop-opacity="0"/>
    <stop offset=".5" stop-color="#fff" stop-opacity=".16"/>
    <stop offset="1" stop-color="#fff" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="tint{pos}" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{color}" stop-opacity=".20"/>
    <stop offset="1" stop-color="{color}" stop-opacity=".03"/>
  </linearGradient>
</defs>
<g class="ti" {d(delay)}>
  <g clip-path="url(#card{pos})">
    <rect width="{TILE_W:.3f}" height="{TILE_H}" fill="{CARD}"/>
    <rect width="{TILE_W:.3f}" height="{TILE_H}" fill="url(#tint{pos})"/>
    <rect x="0" y="0" width="{TILE_W:.3f}" height="2.5" fill="{color}" fill-opacity=".9"/>
    <circle class="rg" {d(delay + 0.5)} cx="{TILE_W - 34:.0f}" cy="{TILE_H - 30}" r="52"
            fill="none" stroke="{color}" stroke-opacity=".45" stroke-width="1.6"/>
    <rect class="sh" style="animation-delay:{delay + 1.4:.2f}s" x="0" y="-20" width="80"
          height="{TILE_H + 40}" fill="url(#gl{pos})" transform="translate(-260 0)"/>
  </g>
  <rect x=".5" y=".5" width="{TILE_W - 1:.3f}" height="{TILE_H - 1}" rx="14" fill="none" stroke="{RULE}"/>
  <text class="sl" {d(delay + 0.35)} x="24" y="38" font-family="{MONO}" font-size="11"
        letter-spacing="1.6" fill="{color}">{label}</text>
  <g class="ai" {d(delay + 0.5)}><text class="n" style="animation-delay:{delay + 1.3:.2f}s"
     x="{TILE_W - 40:.0f}" y="38" font-family="{MONO}" font-size="14" fill="{color}">&#8594;</text></g>
  <g clip-path="url(#slot{pos})"><g class="ro" {d(delay + 0.45)}>
    <text x="20" y="108" font-family="{SERIF}" font-size="46" fill="{color}">{num}
      <tspan font-style="italic" font-size="26" fill="{INK_SOFT}"> {escape(word)}</tspan></text>
  </g></g>
  {blurb_svg}
</g>
"""
    write(
        f"{name}.svg",
        svg(TILE_W, TILE_H, body, ["serif", "serif-i", "sans", "mono"],
            f"{label}: {num} {word}. {blurb}", left=4 * pos, right=8 - 4 * pos),
    )


# ---- 3 · activity -------------------------------------------------------------
def activity(contrib):
    h = 340
    monthly = contrib["monthly"][-12:]
    best = max(monthly[:-1] or monthly, key=lambda m: m["total"])
    top = max(1, best["total"])
    x0, x1, base, maxh, gap = 40, 596, 288, 132, 10
    bw = (x1 - x0 - gap * (len(monthly) - 1)) / len(monthly)

    bars = []
    for i, m in enumerate(monthly):
        partial = i == len(monthly) - 1
        is_best = m is best
        x = x0 + i * (bw + gap)
        delay = 2.2 + i * 0.07
        label = datetime.date.fromisoformat(m["month"] + "-01").strftime("%b")
        if m["total"] > 0:
            bh = max(4, round(m["total"] / top * maxh))
            fill = TECH if is_best else (FAINT if partial else "#41566d")
            bars.append(
                f'<rect class="g" style="animation-delay:{delay:.2f}s" x="{x:.1f}" '
                f'y="{base - bh}" width="{bw:.1f}" height="{bh}" rx="3" fill="{fill}">'
                f'<title>{label}: {m["total"]:,}</title></rect>'
            )
            if is_best:
                bars.append(
                    f'<text class="p" style="animation-delay:3.2s" x="{x + bw / 2:.1f}" '
                    f'y="{base - bh - 10}" text-anchor="middle" font-family="{MONO}" '
                    f'font-size="11" fill="{TECH}">{m["total"]:,}</text>'
                )
        bars.append(
            f'<text class="f" style="animation-delay:{delay:.2f}s" x="{x + bw / 2:.1f}" '
            f'y="{base + 22}" text-anchor="middle" font-family="{MONO}" font-size="10" '
            f'fill="{MUTED}">{label.upper()}</text>'
        )

    cs = contrib["current_streak"]["length"]
    ls = contrib["longest_streak"]["length"]
    note = "current streak" if cs >= ls else f"current streak, longest {ls}"
    unit = "day" if cs == 1 else "days"
    stats = [
        (f'{cs} <tspan font-style="italic">{unit}</tspan>', note),
        (f'{contrib["active_days"]}<tspan fill="{FAINT}"> / {len(contrib["days"])}</tspan>',
         "days with a commit"),
        (f'{contrib["best_day"]["count"]}', "on the busiest day"),
    ]
    side = []
    for i, (big, small) in enumerate(stats):
        y = 104 + i * 78
        side.append(
            f'<g class="r" {d(2.6 + i * 0.15)}>'
            f'<text x="648" y="{y}" font-family="{SERIF}" font-size="40" fill="{INK}">{big}</text>'
            f'<text x="648" y="{y + 22}" font-family="{SANS}" font-size="12" fill="{MUTED}">{small}</text></g>'
        )
        if i < 2:
            side.append(f'<rect class="f" {d(2.6)} x="648" y="{y + 38}" width="188" height="1" fill="{RULE}"/>')

    body = f"""
<rect width="{W}" height="{h}" rx="14" fill="{CARD}"/>
<rect x=".5" y=".5" width="{W - 1}" height="{h - 1}" rx="14" fill="none" stroke="{RULE}"/>
<text class="f" {d(1.9)} x="40" y="58" font-family="{MONO}" font-size="11" letter-spacing="2" fill="{MUTED}">THE LAST 12 MONTHS ON GITHUB</text>
<text class="r" {d(2.0)} x="38" y="118" font-family="{SERIF}" font-size="52" fill="{INK}">{contrib["total_contributions"]:,} <tspan font-style="italic" fill="{TECH}">contributions</tspan></text>
<line class="f" {d(2.1)} x1="{x0 - 6}" y1="{base}" x2="{x1 + 6}" y2="{base}" stroke="{RULE}"/>
{''.join(bars)}
{''.join(side)}
"""
    write(
        "activity.svg",
        svg(W, h, body, ["serif", "serif-i", "sans", "mono"],
            f'{contrib["total_contributions"]:,} contributions in the last year, {cs}-day streak'),
    )


# ---- 4 · repo cards -----------------------------------------------------------
REPO_W, REPO_H = W / 3 - 8, 150


def repo_card(i, repo):
    delay = 4.6 + i * 0.12
    meta = f'{repo["lang"] or "Code"}  &#183;  &#9733; {repo["stars"]}'
    body = f"""
<rect width="{REPO_W:.3f}" height="{REPO_H}" rx="14" fill="{CARD}"/>
<rect x=".5" y=".5" width="{REPO_W - 1:.3f}" height="{REPO_H - 1}" rx="14" fill="none" stroke="{RULE}"/>
<g class="r" {d(delay)}>
  <rect x="24" y="30" width="8" height="8" rx="2" fill="{repo['color']}"/>
  <text x="40" y="39" font-family="{SANS}" font-weight="700" font-size="17" fill="{INK}">{escape(repo["name"])}</text>
  {text_lines(24, 72, wrap(repo["desc"], 34)[:3], 20, f'font-family="{SANS}" font-size="13.5" fill="{INK_SOFT}"')}
  <text x="24" y="{REPO_H - 22}" font-family="{MONO}" font-size="11" fill="{MUTED}">{meta}</text>
</g>
"""
    write(
        f"repo-{repo['name']}.svg",
        svg(REPO_W, REPO_H, body, ["sans", "sans-b", "mono"],
            f'{repo["name"]}: {repo["desc"]}', left=4 * i, right=8 - 4 * i),
    )


# ---- 5 · section title --------------------------------------------------------
def section_title(text, italic):
    body = (
        f'<text class="r" {d(4.4)} x="2" y="46" font-family="{SERIF}" font-size="34" fill="{INK}">'
        f'{escape(text)} <tspan font-style="italic" fill="{TECH}">{escape(italic)}</tspan></text>'
    )
    write("title-coding.svg", svg(W, 64, body, ["serif", "serif-i"], f"{text} {italic}", bottom=0))


# ---- 6 · contribution graph ---------------------------------------------------
BLUE = ["#141b26", "#0d3547", "#11536b", "#187f9f", TECH, "#7defff"]


def level_for(c):
    return 0 if c == 0 else 1 if c <= 5 else 2 if c <= 15 else 3 if c <= 30 else 4 if c <= 50 else 5


def heatmap(contrib):
    days = contrib["days"]
    first = datetime.date.fromisoformat(days[0]["date"])
    lead = (first.weekday() + 1) % 7  # sunday = 0
    cell, step, gx, gy = 12, 15, 44, 96
    cells, months, seen = [], [], set()
    for i, day in enumerate(days):
        col, row = divmod(i + lead, 7)
        date = datetime.date.fromisoformat(day["date"])
        if date.day <= 7 and (date.year, date.month) not in seen and row == 0:
            seen.add((date.year, date.month))
            months.append((col, date.strftime("%b")))
        c = day["count"]
        delay = 1.0 + col * 0.03 + row * 0.02
        cells.append(
            f'<rect class="p" style="animation-delay:{delay:.2f}s" x="{gx + col * step}" '
            f'y="{gy + row * step}" width="{cell}" height="{cell}" rx="3" fill="{BLUE[level_for(c)]}">'
            f'<title>{day["date"]}: {c} contribution{"s" if c != 1 else ""}</title></rect>'
        )
    ncols = (len(days) + lead + 6) // 7
    right = gx + ncols * step - 3
    labels = "".join(
        f'<text x="{gx + col * step}" y="{gy + 7 * step + 16}" font-family="{MONO}" '
        f'font-size="10" fill="{MUTED}">{m.upper()}</text>'
        for col, m in months if col <= ncols - 3
    )
    legend = (
        f'<g class="f" {d(2.4)}>'
        f'<text x="{right - 34 - len(BLUE) * 14 - 8}" y="62" text-anchor="end" '
        f'font-family="{MONO}" font-size="10" letter-spacing="1.2" fill="{FAINT}">LESS</text>'
        + "".join(
            f'<rect x="{right - 34 - len(BLUE) * 14 + i * 14}" y="52" width="11" height="11" '
            f'rx="2.5" fill="{c}"/>'
            for i, c in enumerate(BLUE)
        )
        + f'<text x="{right - 20}" y="62" font-family="{MONO}" font-size="10" '
        f'letter-spacing="1.2" fill="{FAINT}">MORE</text></g>'
    )
    h = gy + 7 * step + 44
    body = f"""
<rect width="{W}" height="{h}" rx="14" fill="{CARD}"/>
<rect x=".5" y=".5" width="{W - 1}" height="{h - 1}" rx="14" fill="none" stroke="{RULE}"/>
<text class="r" {d(0.8)} x="42" y="62" font-family="{SERIF}" font-size="34" fill="{INK}">Every day, <tspan font-style="italic" fill="{TECH}">in blue</tspan></text>
{legend}
{''.join(cells)}
<g class="f" {d(2.4)}>{labels}</g>
"""
    write(
        "heatmap.svg",
        svg(W, h, body, ["serif", "serif-i", "mono"],
            f'Contribution graph: {contrib["total_contributions"]:,} contributions in the last year'),
    )


# ---- data ---------------------------------------------------------------------
LANG_COLOR = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Kotlin": "#A97BFF", "Java": "#b07219", "C": "#555555", "HTML": "#e34c26",
    "CSS": "#563d7c", "Rust": "#dea584", "Go": "#00ADD8", "C++": "#f34b7d",
}
PALETTE = [TECH, STUDIO, LEARN]


def fetch_repos(limit=3):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {"User-Agent": "readme-cards/3.0", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = Request(
            f"https://api.github.com/users/{USERNAME}/repos?per_page=100&sort=updated", headers=headers
        )
        with urlopen(req, timeout=30) as r:
            raw = json.loads(r.read())
    except Exception as e:
        print(f"[warn] repos: {e}")
        return []

    repos = [r for r in raw if not r.get("fork") and r["name"].lower() != USERNAME.lower()]
    repos.sort(key=lambda r: (-r.get("stargazers_count", 0), r["name"]))
    out = []
    for i, r in enumerate(repos[:limit]):
        desc = r.get("description") or f'{r.get("language") or "Code"} project'
        out.append(
            {
                "name": r["name"],
                "desc": desc,
                "stars": r.get("stargazers_count", 0),
                "lang": r.get("language") or "",
                "color": LANG_COLOR.get(r.get("language"), PALETTE[i % len(PALETTE)]),
            }
        )
    return out


def main():
    with open(DATA, encoding="utf-8") as f:
        contrib = json.load(f)
    repos = fetch_repos()
    print(f"data: {contrib['total_contributions']} contributions, {len(repos)} featured repos")

    hero(contrib)
    heatmap(contrib)
    activity(contrib)
    tile("tile-ai", "AI ORCHESTRATION", TECH, "01", "world",
         "Multi-agent systems, MCP tooling and autonomous workflows.", 3.1, 0)
    tile("tile-game", "GAME DEV", STUDIO, "02", "world",
         "AI-driven worlds, procedural generation and LLM NPCs.", 3.35, 1)
    tile("tile-space", "SPACE TECH", LEARN, "03", "world",
         "Cosmic simulations, astronomy data and visualisation.", 3.6, 2)
    section_title("What I'm", "building")
    for i, r in enumerate(repos):
        repo_card(i, r)

    # drop cards for repos that are no longer featured
    keep = {f"repo-{r['name']}.svg" for r in repos}
    for f in os.listdir(OUT):
        if f.startswith("repo-") and f not in keep:
            os.remove(os.path.join(OUT, f))


if __name__ == "__main__":
    main()
