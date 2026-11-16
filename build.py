#!/usr/bin/env python3
"""Builds the HAI Scale site and asset kit into ./site from ./src. Run: python3 build.py"""
import html
import io
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from fontTools import subset
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).parent
SRC = ROOT / "src"
SITE = ROOT / "site"
DATA = json.loads((SRC / "tiers.json").read_text())
TIERS = DATA["tiers"]
BASE = DATA["base_url"]
SANS = SRC / "fonts" / "InstrumentSans.ttf"
SERIF = SRC / "fonts" / "SourceSerif4.ttf"
INK, CREAM, DIAG_LIGHT, DIAG_DARK = "#1E1E1E", "#FAFAF6", "#B3AC9C", "#8A8373"
CIRCLE_PNG_SIZES = [64, 128, 256, 512]
CURRENT = ' aria-current="page"'
_fonts = {}


def font(path, **axes):
    key = (path, tuple(sorted(axes.items())))
    if key not in _fonts:
        _fonts[key] = instancer.instantiateVariableFont(TTFont(path), axes)
    return _fonts[key]


def sans(weight):
    return font(SANS, wght=weight, wdth=100)


def serif(weight, opsz=60):
    return font(SERIF, wght=weight, opsz=opsz)


def cap_offset(f):
    """Half the cap height in em: the baseline offset that centres capitals on a point."""
    return f["OS/2"].sCapHeight / f["head"].unitsPerEm / 2


def text_path(text, size, x, y, f, anchor="start", fill=INK, tracking=0.0, centre=False):
    """Text as an outlined <path>, so badges and logos render the same with no font installed."""
    glyphs, cmap, hmtx = f.getGlyphSet(), f.getBestCmap(), f["hmtx"]
    scale = size / f["head"].unitsPerEm
    if centre:
        y = y + cap_offset(f) * size
    names = [cmap.get(ord(ch), ".notdef") for ch in text]
    width = sum(hmtx[n][0] for n in names) * scale + tracking * (len(names) - 1)
    cx = x - (width / 2 if anchor == "middle" else 0)
    pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    for n in names:
        glyphs[n].draw(TransformPen(pen, (scale, 0, 0, -scale, cx, y)))
        cx += hmtx[n][0] * scale + tracking
    return f'<path fill="{fill}" d="{pen.getCommands()}"/>', width


def label(t):
    return f"{t['code']} · {t['name']}"


def alt(t):
    return f"HAI Scale: {t['code']} — {t['name']}"


def chip_label(t):
    return f"{t['code']}  ·  {t['name']}"


def chip_width(t):
    return round(34 + text_path(chip_label(t), 13, 0, 0, sans(600))[1] + 14)


def chip_svg(t, dark=False):
    w = chip_width(t)
    bg, border, ink = ("#1E1E1C", "#45433C", CREAM) if dark else (CREAM, "#E7E2D6", INK)
    code = text_path(t["code"], 9.5, 16, 16, sans(700), "middle", t["text"], centre=True)[0]
    lab = text_path(chip_label(t), 13, 34, 16, sans(600), fill=ink, centre=True)[0]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="32" viewBox="0 0 {w} 32" role="img" aria-label="{alt(t)}">
<title>{alt(t)}</title>
<rect x="0.5" y="0.5" width="{w - 1}" height="31" rx="15.5" fill="{bg}" stroke="{border}"/>
<circle cx="16" cy="16" r="11" fill="{t['color']}"/>
{code}
{lab}
</svg>
'''


def circle_svg(t, with_text=True):
    fs = 36 if len(t["code"]) == 1 else 32
    text = text_path(t["code"], fs, 50, 50, sans(700), "middle", t["text"], centre=True)[0] + "\n" if with_text else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100" role="img" aria-label="{alt(t)}">
<title>{alt(t)}</title>
<circle cx="50" cy="50" r="50" fill="{t['color']}"/>
{text}</svg>
'''


# Logo geometry on a 100 grid (glyph spans 14–86). The grey diagonal is drawn first so the ink strokes sit over it.
# Strokes are 13 units; the diagonal is widened so its perpendicular thickness matches.
MARK_SHAPES = (
    '<polygon class="diag" points="14,14 28.65,14 66,86 51.35,86" fill="{diag}"/>'
    '<rect class="ink" x="14" y="14" width="13" height="72" fill="{ink}"/>'
    '<rect class="ink" x="20.5" y="43.5" width="43.5" height="13" fill="{ink}"/>'
    '<rect class="ink" x="73" y="14" width="13" height="72" fill="{ink}"/>'
)


def mark_svg(ink=INK, diag=DIAG_LIGHT, bg=None, square=False):
    shapes = MARK_SHAPES.format(ink=ink, diag=diag)
    if square:
        rect = f'<rect width="100" height="100" rx="22" fill="{bg}"/>' if bg else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 100 100" role="img" aria-label="HAI Scale">'
                f'<title>HAI Scale</title>{rect}<g transform="translate(13 13) scale(0.74)">{shapes}</g></svg>\n')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="4 4 92 92" role="img" aria-label="HAI Scale">'
            f'<title>HAI Scale</title>{shapes}</svg>\n')


def bare_shapes():
    return MARK_SHAPES.format(ink="", diag="").replace(' fill=""', "")


def favicon_svg():
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="8 8 84 84"><style>.ink{fill:#1E1E1E}.diag{fill:#B3AC9C}'
            '@media(prefers-color-scheme:dark){.ink{fill:#FAFAF6}.diag{fill:#8A8373}}</style>' + bare_shapes() + '</svg>\n')


def inline_mark():
    return '<svg class="mark" viewBox="12 12 76 76" aria-hidden="true">' + bare_shapes() + '</svg>'


def lockup_svg(ink=INK, diag=DIAG_LIGHT):
    shapes = MARK_SHAPES.format(ink=ink, diag=diag)
    word, width = text_path("HAI Scale", 50, 106, 50, serif(500), fill=ink, tracking=-0.6, centre=True)
    w = round(106 + width + 14)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w * 2}" height="200" viewBox="0 0 {w} 100" role="img" aria-label="HAI Scale">'
            f'<title>HAI Scale</title>{shapes}{word}</svg>\n')


def og_svg():
    circles = ""
    x = 96
    for t in TIERS:
        circles += f'<circle cx="{x + 40}" cy="486" r="40" fill="{t["color"]}"/>'
        circles += text_path(t["code"], 28, x + 40, 486, sans(700), "middle", t["text"], centre=True)[0]
        x += 100
    bar = "".join(f'<rect x="{i * 1200 / 7:.2f}" y="0" width="{1200 / 7 + 0.5:.2f}" height="8" fill="{t["color"]}"/>' for i, t in enumerate(TIERS))
    shapes = MARK_SHAPES.format(ink=INK, diag=DIAG_LIGHT)
    head = text_path("Say how much AI made it", 84, 96, 316, serif(400), tracking=-1.4)[0]
    sub = text_path("A voluntary, self-declared label · seven tiers from fully human to fully automated", 28, 96, 374, sans(400), fill="#5A554D")[0]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">'
            f'<rect width="1200" height="630" fill="{CREAM}"/>{bar}<g transform="translate(82 72) scale(1.3)">{shapes}</g>'
            f'{head}{sub}{circles}</svg>\n')


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def chip_html(t, href=None):
    tag, attr = ("a", f' href="{href}"') if href else ("span", "")
    return (f'<{tag} class="chip"{attr}><span class="sw" style="background:{t["color"]};color:{t["text"]}">{t["code"]}</span>'
            f'<span class="lb">{t["code"]}<span class="dot">·</span>{html.escape(t["name"])}</span></{tag}>')


def circle_html(t, href=None, cls="circle"):
    tag, attr = ("a", f' href="{href}" aria-label="{html.escape(alt(t))}"') if href else ("span", "")
    return f'<{tag} class="{cls}"{attr} style="background:{t["color"]};color:{t["text"]}">{t["code"]}</{tag}>'


def tag_html(t):
    return (f'<span class="tag" style="background:{t["color"]};color:{t["text"]}" '
            f'title="{html.escape(alt(t))}">{t["code"]}</span>')


CODE_RE = re.compile(r"\b(" + "|".join(sorted((t["code"] for t in TIERS), key=len, reverse=True)) + r")\b")


def tag_codes(text):
    by_code = {t["code"]: t for t in TIERS}
    return CODE_RE.sub(lambda m: tag_html(by_code[m.group(1)]), text)


def render(template, **values):
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", value)
    by_code = {t["code"]: t for t in TIERS}
    topline = ('<div class="topline" aria-hidden="true">'
               + "".join(f'<span style="background:{t["color"]}"></span>' for t in TIERS) + '</div>')
    out = out.replace("{{TOPLINE}}", topline)
    return re.sub(r"\{\{T:(\w+)\}\}", lambda m: tag_html(by_code[m.group(1)]), out)


def build_assets():
    for t in TIERS:
        c = t["code"]
        write(SITE / "badge" / f"{c}.svg", chip_svg(t))
        write(SITE / "badge" / f"{c}-dark.svg", chip_svg(t, dark=True))
        write(SITE / "badge" / "circle" / f"{c}.svg", circle_svg(t))
        write(SITE / "badge" / "dot" / f"{c}.svg", circle_svg(t, with_text=False))
    logo = SITE / "logo"
    write(logo / "hai-mark.svg", mark_svg())
    write(logo / "hai-mark-dark.svg", mark_svg(CREAM, DIAG_DARK))
    write(logo / "hai-mark-mono-black.svg", mark_svg("#000000", "#A0A0A0"))
    write(logo / "hai-icon.svg", mark_svg(INK, DIAG_LIGHT, bg=CREAM, square=True))
    write(logo / "hai-icon-dark.svg", mark_svg(CREAM, DIAG_DARK, bg=INK, square=True))
    write(logo / "hai-lockup.svg", lockup_svg())
    write(logo / "hai-lockup-dark.svg", lockup_svg(CREAM, DIAG_DARK))
    write(SITE / "favicon.svg", favicon_svg())
    write(SITE / "og.src.svg", og_svg())


def export_rasters():
    acts = []

    def png(src, dst, width):
        acts.append(f"file-open:{src};export-type:png;export-filename:{dst};export-width:{width};export-do;file-close")

    def pdf(src, dst):
        acts.append(f"file-open:{src};export-type:pdf;export-text-to-path;export-filename:{dst};export-do;file-close")

    b = SITE / "badge"
    for d in ("png", "pdf"):
        (b / d).mkdir(parents=True, exist_ok=True)
        (b / "circle" / d).mkdir(parents=True, exist_ok=True)
    for t in TIERS:
        c = t["code"]
        for suffix in ("", "-dark"):
            w = chip_width(t)
            png(b / f"{c}{suffix}.svg", b / "png" / f"{c}{suffix}@2x.png", w * 2)
            png(b / f"{c}{suffix}.svg", b / "png" / f"{c}{suffix}@4x.png", w * 4)
        for s in CIRCLE_PNG_SIZES:
            png(b / "circle" / f"{c}.svg", b / "circle" / "png" / f"{c}-{s}.png", s)
        pdf(b / f"{c}.svg", b / "pdf" / f"{c}.pdf")
        pdf(b / "circle" / f"{c}.svg", b / "circle" / "pdf" / f"{c}.pdf")
    logo = SITE / "logo"
    for name in ("hai-mark", "hai-mark-dark", "hai-icon", "hai-icon-dark"):
        png(logo / f"{name}.svg", logo / f"{name}-512.png", 512)
    png(logo / "hai-lockup-dark.svg", logo / "hai-lockup-dark-1200.png", 1200)
    png(logo / "hai-lockup.svg", logo / "hai-lockup-1200.png", 1200)
    png(logo / "hai-icon.svg", SITE / "apple-touch-icon.png", 180)
    png(logo / "hai-icon.svg", SITE / "favicon-32.png", 32)
    png(SITE / "og.src.svg", SITE / "og.png", 1200)
    for i in range(0, len(acts), 25):
        subprocess.run(["inkscape", "--actions=" + ";".join(acts[i:i + 25])], check=True, capture_output=True)
    (SITE / "og.src.svg").unlink()


def build_webfont():
    keep = [*range(0x20, 0x7F), *range(0xA0, 0x100), 0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026, 0x2190, 0x2192]
    out = SITE / "fonts"
    out.mkdir(parents=True, exist_ok=True)
    for src, pin, name in ((SANS, {"wdth": 100}, "InstrumentSans"), (SERIF, {}, "SourceSerif4")):
        buf = io.BytesIO()
        (instancer.instantiateVariableFont(TTFont(src), pin) if pin else TTFont(src)).save(buf)
        buf.seek(0)
        vf = TTFont(buf)
        sub = subset.Subsetter(subset.Options(layout_features=["*"]))
        sub.populate(unicodes=keep)
        sub.subset(vf)
        vf.flavor = "woff2"
        vf.save(out / f"{name}.woff2")
    for lic in ("OFL-InstrumentSans.txt", "OFL-SourceSerif4.txt"):
        shutil.copy(SRC / "fonts" / lic, out / lic)


def md_to_html(md):
    """Just enough Markdown for the licence: headings, paragraphs, bullet lists, bold, links."""
    def inline(text):
        text = html.escape(text, quote=False)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        return re.sub(r"(https://[^\s<]+[^\s<.,;:)])", r'<a href="\1">\1</a>', text)
    out, para, items = [], [], []
    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>"); para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>"); items.clear()
    for line in md.splitlines():
        if not line.strip():
            flush()
        elif line.startswith("#"):
            flush()
            level = len(line) - len(line.lstrip("#"))
            out.append(f"<h{level}>{inline(line.lstrip('#').strip())}</h{level}>")
        elif line.startswith("- "):
            if para:
                flush()
            items.append(line[2:])
        else:
            para.append(line.strip())
    flush()
    return "\n".join(out)


def build_license():
    md = (ROOT / "LICENSE.md").read_text()
    write(SITE / "LICENSE.md", md)
    body = md_to_html(md).replace("<h1>HAI Scale License 1.0</h1>", "")
    page = render((SRC / "license.template.html").read_text(), MARK=inline_mark(), BODY=body, VERSION=DATA["version"])
    write(SITE / "license" / "index.html", page)


def build_pages():
    by_code = {t["code"]: t for t in TIERS}
    shutil.copy(SRC / "style.css", SITE / "style.css")
    shutil.copy(SRC / "_headers", SITE / "_headers")
    shutil.copy(SRC / "autograph.svg", SITE / "autograph.svg")
    mark = inline_mark()
    hero_rows = "\n".join(
        f'<a class="lrow" href="{t["code"]}/">{circle_html(t, cls="circle sm")}'
        f'<span class="nm">{html.escape(t["name"])}</span></a>'
        for t in TIERS
    )
    disclosure = json.loads((SRC / "disclosure.json").read_text())
    made_rows = "\n".join(
        f'<li><div class="mp"><span class="pt">{html.escape(d["part"])}</span><span class="pd">{html.escape(d["detail"])}</span></div>'
        f'<div class="mc">{chip_html(by_code[d["tier"]], d["tier"] + "/")}</div><p class="mn">{html.escape(d["note"])}</p></li>'
        for d in disclosure["parts"]
    )
    rows = "\n".join(
        f'<a class="row" href="{t["code"]}/">{circle_html(t)}<span class="nm">{html.escape(t["name"])}</span>'
        f'<span class="ds">{html.escape(t["short"])}</span><span class="go" aria-hidden="true">→</span></a>'
        for t in TIERS
    )
    asset_rows = "\n".join(
        f'<tr><td>{chip_html(t)}</td><td class="files"><a href="badge/{c}.svg">SVG</a><a href="badge/{c}-dark.svg">SVG dark</a>'
        f'<a href="badge/png/{c}@2x.png">PNG</a><a href="badge/pdf/{c}.pdf">PDF</a></td>'
        f'<td class="files"><a href="badge/circle/{c}.svg">SVG</a><a href="badge/circle/png/{c}-256.png">PNG</a>'
        f'<a href="badge/dot/{c}.svg">Dot</a></td></tr>'
        for t in TIERS for c in [t["code"]]
    )
    index = render(
        (SRC / "index.template.html").read_text(),
        MARK=mark, HERO_ROWS=hero_rows, MADE_ROWS=made_rows, SCALE_ROWS=rows, ASSET_ROWS=asset_rows,
        TIERS_JSON=json.dumps(TIERS), BASE=BASE, VERSION=DATA["version"],
        SITE_CHIP=chip_html(by_code["M2"], "M2/"), DESIGN_CHIP=chip_html(by_code["HC"], "HC/"),
        EX_CHIP=chip_html(TIERS[2], "M1/"), EX_CIRCLE=circle_html(TIERS[5]),
    )
    write(SITE / "index.html", index)

    tier_tpl = (SRC / "tier.template.html").read_text()
    for i, t in enumerate(TIERS):
        c = t["code"]
        ladder = "".join(
            f'<a href="../{o["code"]}/" style="background:{o["color"]};color:{o["text"]}"'
            f'{CURRENT if o is t else ""} aria-label="{html.escape(alt(o))}">{o["code"]}</a>'
            for o in TIERS
        )
        neighbours = []
        if i > 0:
            p = TIERS[i - 1]
            neighbours.append(f'<a class="chip plain" href="../{p["code"]}/">← {html.escape(label(p))}</a>')
        if i < len(TIERS) - 1:
            n = TIERS[i + 1]
            neighbours.append(f'<a class="chip plain" href="../{n["code"]}/">{html.escape(label(n))} →</a>')
        page = render(
            tier_tpl, MARK=mark, CODE=c, NAME=html.escape(t["name"]), ALT=html.escape(alt(t)),
            COLOR=t["color"], TEXT=t["text"], MEANS=html.escape(t["means"]), SHORT=html.escape(t["short"]),
            EXAMPLES="".join(f"<li>{html.escape(e)}</li>" for e in t["examples"]),
            BOUNDARY=tag_codes(html.escape(t["boundary"])), LADDER=ladder, NEIGHBOURS="".join(neighbours),
            CHIP=chip_html(t), BASE=BASE, VERSION=DATA["version"],
            HTML_SNIPPET=html.escape(f'<a href="{BASE}/{c}/"><img src="{BASE}/badge/{c}.svg" alt="{alt(t)}" height="32"></a>'),
            MD_SNIPPET=html.escape(f'[![{alt(t)}]({BASE}/badge/{c}.svg)]({BASE}/{c}/)'),
        )
        write(SITE / c / "index.html", page)

    public = {k: DATA[k] for k in ("name", "long_name", "version", "base_url")}
    public["license"] = {"name": "HAI Scale License 1.0", "url": f"{BASE}/license/"}
    public["tiers"] = [
        {**{k: t[k] for k in ("code", "name", "color", "short", "means")}, "text_color": t["text"],
         "url": f"{BASE}/{t['code']}/", "badge": f"{BASE}/badge/{t['code']}.svg",
         "circle": f"{BASE}/badge/circle/{t['code']}.svg"}
        for t in TIERS
    ]
    write(SITE / "hai.json", json.dumps(public, indent=2, ensure_ascii=False) + "\n")


AGENT_NOTE = ("Using an AI to choose the tier or to insert the badge does not count as AI use. "
              "The tier describes how the content was made, not how the label was added.")


def agent_guide():
    tiers = "\n".join(f"| `{t['code']}` | {t['name']} | {t['means']} |" for t in TIERS)
    bounds = "\n".join(f"- `{t['code']}`: {t['boundary']}" for t in TIERS)
    return f"""# HAI Scale: instructions for AI agents

The HAI Scale (Human–AI Index) v{DATA['version']} is a seven-tier label that discloses how much AI was used to make a piece of content. This file tells you, an AI agent, how to choose the right tier for the work you are helping with and how to add its badge.

Canonical copy: {BASE}/agents.md · Machine-readable scale: {BASE}/hai.json

## What the badge covers

The badge describes the **content**: the article, code, image, video or document being published.

**{AGENT_NOTE}** A hand-written essay that you label on the author's behalf is still `H`.

## Tiers

| Code | Name | Meaning |
|---|---|---|
{tiers}

## Choosing the tier

Answer these about the content, in order, and stop at the first match:

1. Was any AI used on the content at any point, even only to check it? No: `H`.
2. Did AI add or change any content, beyond minor fixes such as grammar, typos or simple rewording? No: `HC`.
3. Who produced most of the finished work? Mostly the person, with AI changes late on: `M1`. About half each: `M2`.
4. Mostly AI. How involved was a person? Steering, testing and verifying throughout: `A1`. Prompts, then one final check: `A2`. Nobody reviewed it before release: `AF`.

Boundaries:

{bounds}

Rules:

- Count your own contribution honestly. If you wrote most of the content in this session, that is `A1`, `A2` or `AF` depending on how closely the person reviewed it.
- You only know what happened in your own session. If earlier work or the person's own process is unknown, ask them. Do not guess.
- When torn between two tiers, choose the more automated one.
- If a badge already exists and your work changes the picture (for example, you rewrote half of an `H` document), tell the person and propose the new tier rather than leaving the old one.
- If parts differ a lot, label them separately, for example text `H` and illustrations `A2`.
- Tell the person which tier you chose and why, so they can correct it. It is their declaration.

## Adding the badge

Replace `CODE` with the tier code and `NAME` with its name. Put the badge where people start: byline, top of the README, title page, first seconds of a video.

| Where | What to add |
|---|---|
| GitHub README, Markdown | `[![HAI Scale: CODE — NAME]({BASE}/badge/CODE.svg)]({BASE}/CODE/)` |
| Web page | `<a href="{BASE}/CODE/"><img src="{BASE}/badge/CODE.svg" alt="HAI Scale: CODE — NAME" height="32"></a>` and, in `<head>`, `<meta name="hai-scale" content="CODE">` |
| Dark background | Use `{BASE}/badge/CODE-dark.svg` |
| Source file | A comment on the first lines: `HAI Scale: CODE — NAME · {BASE}/CODE/` |
| Plain text, email, social post, video description | `HAI Scale: CODE — NAME · {BASE}/CODE/` |
| Document or slides | Image `{BASE}/badge/png/CODE@4x.png`, linked to `{BASE}/CODE/` |
| Image or video overlay, small icon | `{BASE}/badge/circle/CODE.svg` or `{BASE}/badge/circle/png/CODE-512.png` |

Do not recolour or redraw the badge.

## Licence

The Scale is free to use under the HAI Scale License 1.0 ({BASE}/license/): label truthfully, keep the tiers and badges intact, and do not sell access to the Scale itself.
"""


def build_agent_files():
    guide = agent_guide()
    write(SITE / "agents.md", guide)
    write(SITE / "llms.txt", f"# HAI Scale\n\n> {DATA['long_name']}: a seven-tier label for disclosing how much AI was used to make something.\n\n"
          f"- [Instructions for AI agents]({BASE}/agents.md): choose a tier and add the badge\n"
          f"- [Scale definition]({BASE}/hai.json)\n")


def build_examples():
    ex = SITE / "examples"
    if (SRC / "examples").exists():
        shutil.copytree(SRC / "examples", ex, dirs_exist_ok=True)


def build_zip():
    target = SITE / "hai-scale-kit.zip"
    target.unlink(missing_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for folder in ("badge", "logo"):
            for f in sorted((SITE / folder).rglob("*")):
                if f.is_file():
                    z.write(f, Path("hai-scale-kit") / f.relative_to(SITE))
        for name in ("hai.json", "agents.md", "LICENSE.md"):
            z.write(SITE / name, f"hai-scale-kit/{name}")


if __name__ == "__main__":
    if SITE.exists():
        shutil.rmtree(SITE)
    build_assets()
    export_rasters()
    build_webfont()
    build_pages()
    build_license()
    build_examples()
    build_agent_files()
    build_zip()
    print(f"Built {sum(1 for f in SITE.rglob('*') if f.is_file())} files into {SITE}")
