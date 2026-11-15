"""Build the six-slide demo PDF and editable PowerPoint from local screenshots."""
from html import escape
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt
from playwright.sync_api import sync_playwright
from PIL import Image

HERE = Path(__file__).resolve().parent
SITE = "https://yashneil75.github.io/califire/"
INK, MUTED, BLUE, EMBER = "17202A", "596575", "0868D7", "BD4D29"
CREAM, WHITE, LINE = "F8F6F1", "FFFFFF", "DDD8CF"

SLIDES = [
    ("01 / THE IDEA", "California,\nday by day.",
     "A satellite fire-activity calendar for exploring California's past and present.",
     ["NASA Space Apps Challenge 2026", "Harmonization of MODIS and VIIRS Hot Spots"], "calendar.png"),
    ("02 / THE PROBLEM", "One fire record.\nDifferent sensors.",
     "MODIS and VIIRS observe at different resolutions, sensitivities and times. Raw detections cannot simply be compared as one continuous record.",
     ["MODIS: longer history", "VIIRS: finer detection", "Our focus: California"], None),
    ("03 / THE METHOD", "From observations\nto an activity index.",
     "NASA FIRMS hotspots are filtered to California and grouped into satellite passes.",
     ["1  Filter detection centres to the state", "2  Count occupied 1 km grid cells", "3  Estimate MODIS-Aqua-like activity from VIIRS", "4  Sum passes by day; refresh the calendar and map"], None),
    ("04 / THE CALENDAR", "Explore a day.\nSee the context.",
     "Open any reported day to inspect the activity index, radiative power and day/night observations.",
     ["Daily calendar", "Day and night breakdown", "Historical context"], "calendar.png"),
    ("05 / THE ARCHIVE", "See the pattern\nacross years.",
     "Compare months across the archive, then explore where the reported activity is concentrated on the map.",
     ["Monthly archive from 2000", "Interactive California map", "Year-range controls"], "archive.png"),
    ("06 / USE WITH CARE", "Useful context.\nClear limits.",
     "An experimental activity index—not burned area, a fire count, a forecast or an emergency alert.",
     ["Blank days do not mean zero fire.", "NOAA-20 estimates are provisional.", "NASA FIRMS · Source Cooperative · Natural Earth", "AI-assisted development: Codex, Claude Code, OpenCode"], "map.png"),
]


def color(hexcode):
    return RGBColor.from_string(hexcode)


def text_box(slide, text, x, y, w, h, size, *, shade=INK, bold=False):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shape.text_frame
    tf.clear(); tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.01)
    tf.margin_top = tf.margin_bottom = Inches(0.01)
    for i, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.name = "Aptos"
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = color(shade)
        p.space_after = Pt(2)
    return shape


def rect(slide, x, y, w, h, fill, *, border=None):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = color(fill)
    if border:
        s.line.color.rgb = color(border)
    else:
        s.line.fill.background()
    return s


def powerpoint():
    prs = Presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    for number, (label, title, subtitle, bullets, img) in enumerate(SLIDES, 1):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.background.fill.solid(); slide.background.fill.fore_color.rgb = color(CREAM)
        rect(slide, .55, .48, .12, .24, EMBER)
        text_box(slide, label, .85, .48, 4.8, .28, 11, shade=EMBER, bold=True)
        text_box(slide, title, .85, 1.0, 6.0, 1.5, 34, bold=True)
        text_box(slide, subtitle, .87, 2.6, 5.15, 1.05, 17, shade=MUTED)
        start = 4.0 if len(bullets) <= 3 else 3.85
        for i, item in enumerate(bullets):
            rect(slide, .9, start + i*.43, .08, .08, BLUE)
            text_box(slide, item, 1.12, start - .07 + i*.43, 5.15, .4, 14, shade=INK)
        if img:
            rect(slide, 6.6, 1.04, 6.12, 4.95, WHITE, border=LINE)
            image_path = HERE / 'assets' / img
            with Image.open(image_path) as screenshot:
                width, height = screenshot.size
            shown_w = min(5.92, 4.75 * width / height)
            shown_h = shown_w * height / width
            slide.shapes.add_picture(str(image_path), Inches(6.7 + (5.92-shown_w)/2),
                                     Inches(1.14 + (4.75-shown_h)/2), width=Inches(shown_w))
        else:
            rect(slide, 6.6, 1.04, 6.12, 4.95, WHITE, border=LINE)
            if number == 2:
                text_box(slide, "2000  →  2011", 7.1, 1.65, 4.8, .55, 25, bold=True)
                text_box(slide, "MODIS observations", 7.1, 2.18, 4.8, .4, 16, shade=MUTED)
                rect(slide, 7.1, 2.85, 4.85, .04, LINE)
                text_box(slide, "2012  →  PRESENT", 7.1, 3.2, 4.8, .55, 25, bold=True, shade=BLUE)
                text_box(slide, "VIIRS activity estimates", 7.1, 3.75, 4.8, .4, 16, shade=MUTED)
                text_box(slide, "Sensor and coverage differences remain.", 7.1, 4.6, 5.0, .5, 14, shade=EMBER)
            else:
                for i, (head, body) in enumerate([( "NASA FIRMS", "MODIS + VIIRS detections"), ("CALIFORNIA", "State boundary + 1 km grid"), ("MODEL", "MODIS-Aqua-like estimates"), ("EXPLORE", "Calendar + archive + map")]):
                    yy = 1.42 + i * 1.02
                    text_box(slide, head, 7.1, yy, 4.8, .3, 12, shade=BLUE, bold=True)
                    text_box(slide, body, 7.1, yy+.32, 4.9, .35, 16)
        text_box(slide, "CALIFIRE", .85, 6.93, 4.5, .25, 10, shade=MUTED, bold=True)
        link = text_box(slide, "OPEN THE LIVE PROJECT  ↗", 8.7, 6.9, 3.6, .3, 11, shade=BLUE, bold=True)
        link.text_frame.paragraphs[0].runs[0].hyperlink.address = SITE
        text_box(slide, f"{number:02d} / 06", 12.1, 6.92, .7, .25, 10, shade=MUTED)
    output = HERE / "Califire-Demo.pptx"
    prs.save(output)
    assert len(prs.slides) == 6
    print('Created', output)


def pdf():
    pages = []
    for number, (label, title, subtitle, bullets, img) in enumerate(SLIDES, 1):
        items = ''.join(f'<li>{escape(b)}</li>' for b in bullets)
        if img:
            right = f'<div class="picture"><img src="assets/{img}"></div>'
        elif number == 2:
            right = '<div class="panel"><strong>2000 → 2011</strong><span>MODIS observations</span><hr><strong class="blue">2012 → PRESENT</strong><span>VIIRS activity estimates</span><p>Sensor and coverage differences remain.</p></div>'
        else:
            right = '<div class="panel steps"><b>NASA FIRMS</b><span>MODIS + VIIRS detections</span><b>CALIFORNIA</b><span>State boundary + 1 km grid</span><b>MODEL</b><span>MODIS-Aqua-like estimates</span><b>EXPLORE</b><span>Calendar + archive + map</span></div>'
        pages.append(f'<section><div class="label">{escape(label)}</div><div class="left"><h1>{escape(title).replace(chr(10),"<br>")}</h1><p class="subtitle">{escape(subtitle)}</p><ul>{items}</ul></div>{right}<footer><b>CALIFIRE</b><a href="{SITE}">OPEN THE LIVE PROJECT ↗</a><span>{number:02} / 06</span></footer></section>')
    html = '''<!doctype html><html><head><meta charset="utf-8"><style>
      @page { size: 13.333in 7.5in; margin: 0 } * {box-sizing:border-box}
      body {margin:0; font-family:Arial,sans-serif; color:#17202a}
      section {position:relative; width:13.333in;height:7.5in;overflow:hidden;background:#f8f6f1;page-break-after:always}
      section:last-child {page-break-after:auto}.label {position:absolute;left:.85in;top:.49in;font-size:11pt;font-weight:700;color:#bd4d29;letter-spacing:.04em}
      .label:before {content:"";position:absolute;left:-.3in;top:0;width:.12in;height:.22in;background:#bd4d29}
      .left {position:absolute;left:.85in;top:1.0in;width:5.15in} h1 {font-size:34pt;line-height:1.12;letter-spacing:-.03em;margin:0;height:1.45in}
      .subtitle {font-size:17pt;line-height:1.3;color:#596575;margin:.15in 0 0;height:1.2in}
      ul {list-style:none;margin:.2in 0 0;padding:0;font-size:14pt}li {position:relative;margin:0 0 .22in .27in}li:before {content:"";position:absolute;left:-.23in;top:.08in;width:.08in;height:.08in;background:#0868d7}
      .picture,.panel {position:absolute;left:6.6in;top:1.04in;width:6.12in;height:4.95in;background:white;border:1px solid #ddd8cf}
      .picture {padding:.1in;display:flex;align-items:center;justify-content:center}.picture img {width:100%;height:100%;object-fit:contain}
      .panel {padding:.55in}.panel strong {display:block;font-size:25pt;margin:.1in 0}.panel span {display:block;color:#596575;font-size:16pt}.panel hr {border:0;border-top:1px solid #ddd8cf;margin:.5in 0}.panel p{color:#bd4d29;font-size:14pt;margin-top:.5in}.blue,.steps b{color:#0868d7}.steps b{display:block;font-size:12pt;margin:.08in 0}.steps span{margin-bottom:.28in;color:#17202a}
      footer{position:absolute;bottom:.34in;left:.85in;right:.55in;font-size:10pt;color:#596575;display:flex;align-items:center;justify-content:space-between}
      footer a{font-size:11pt;font-weight:bold;color:#0868d7;text-decoration:none;margin-left:auto;margin-right:.7in}
    </style></head><body>''' + ''.join(pages) + '</body></html>'
    path = HERE / 'demo-slides.html'; path.write_text(html, encoding='utf-8')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(path.as_uri(), wait_until='load')
        page.pdf(path=str(HERE / 'Califire-Demo.pdf'), print_background=True, prefer_css_page_size=True)
        browser.close()
    print('Created PDF')


if __name__ == '__main__':
    powerpoint()
    pdf()
