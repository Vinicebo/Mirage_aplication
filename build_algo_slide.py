"""
Builds a single-slide deck explaining the Mirage recommendation algorithm (algorithm.py).
Run: py build_algo_slide.py
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

OUT = "Mirage_Recommendation_Algorithm_Slide.pptx"

CHARCOAL = RGBColor(26, 26, 27)
MUTED = RGBColor(113, 113, 113)
ACCENT = RGBColor(106, 133, 116)
LINE = RGBColor(235, 235, 234)
CREAM = RGBColor(247, 246, 244)
WHITE = RGBColor(255, 255, 255)


def add_p(slide, left, top, width, height, lines, title=None, title_size=16, body_size=12):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    if title:
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(title_size)
        p.font.bold = True
        p.font.color.rgb = CHARCOAL
        p.space_after = Pt(6)
        start = 1
    else:
        start = 0
    for i, line in enumerate(lines):
        if i == 0 and not title:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = line
        p.font.size = Pt(body_size)
        p.font.color.rgb = MUTED
        p.space_after = Pt(3)
    return box


def main():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = CREAM
    bg.line.fill.background()

    accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.12), prs.slide_height)
    accent.fill.solid()
    accent.fill.fore_color.rgb = ACCENT
    accent.line.fill.background()

    t = slide.shapes.add_textbox(Inches(0.55), Inches(0.38), Inches(12.2), Inches(0.85))
    p = t.text_frame.paragraphs[0]
    p.text = "How the recommendation algorithm works"
    p.font.size = Pt(38)
    p.font.bold = True
    p.font.color.rgb = CHARCOAL

    st = slide.shapes.add_textbox(Inches(0.55), Inches(1.12), Inches(12.2), Inches(0.45))
    sp = st.text_frame.paragraphs[0]
    sp.text = (
        "Rule-based prioritization for corporate furniture leads (Rio de Janeiro) — "
        "not machine learning; transparent scoring you can explain to sales."
    )
    sp.font.size = Pt(14)
    sp.font.color.rgb = MUTED

    y = Inches(1.75)
    col_w = Inches(3.95)
    gap = Inches(0.28)
    x0 = Inches(0.55)
    h = Inches(4.35)

    for i in range(3):
        x = x0 + i * (col_w + gap)
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, col_w, h)
        card.fill.solid()
        card.fill.fore_color.rgb = WHITE
        card.line.color.rgb = LINE
        card.line.width = Pt(0.75)
        try:
            card.adjustments[0] = 0.04
        except Exception:
            pass

    add_p(
        slide,
        x0 + Inches(0.18),
        y + Inches(0.2),
        col_w - Inches(0.36),
        h - Inches(0.35),
        [
            "NewsAPI: Portuguese queries (new office, expansion, RJ).",
            "Headlines matched to trigger types (e.g. relocation).",
            "RSS: public procurement titles with furniture keywords.",
            "Triggers attach to existing leads or create new candidates.",
        ],
        title="1 — Discover signals",
        title_size=17,
        body_size=11.5,
    )

    x1 = x0 + col_w + gap
    add_p(
        slide,
        x1 + Inches(0.18),
        y + Inches(0.2),
        col_w - Inches(0.36),
        h - Inches(0.35),
        [
            "BrasilAPI: CNPJ → main activity (CNAE) → industry bucket.",
            "Employee / budget proxies from registry where available.",
            "IBGE-style call supplies a simple seasonal multiplier on urgency.",
            "24-hour JSON cache reduces repeat API calls.",
        ],
        title="2 — Enrich",
        title_size=17,
        body_size=11.5,
    )

    x2 = x0 + 2 * (col_w + gap)
    add_p(
        slide,
        x2 + Inches(0.18),
        y + Inches(0.2),
        col_w - Inches(0.36),
        h - Inches(0.35),
        [
            "Fit: industry vs. Mirage “ideal” sectors (0–10 pts).",
            "Size: headcount thresholds (0–10 pts).",
            "Urgency: base + recent trigger, × seasonal (~0–10+ pts).",
            "Total ≈ 30 → Tier A (≥25), B (≥18), C — sorted high→low.",
            "Architects: separate score (past deals ×2 + momentum×10).",
        ],
        title="3 — Score & tier",
        title_size=17,
        body_size=11.5,
    )

    foot = slide.shapes.add_textbox(Inches(0.55), Inches(6.35), Inches(12.2), Inches(0.55))
    fp = foot.text_frame.paragraphs[0]
    fp.text = "Output: ranked leads.json + CSV + monthly-style report  •  Full automation optional; scoring-only mode if APIs are off."
    fp.font.size = Pt(12)
    fp.font.color.rgb = MUTED

    notes = slide.notes_slide.notes_text_frame
    notes.text = SPEAKER_NOTES

    prs.save(OUT)
    print("Wrote", OUT)


SPEAKER_NOTES = """SPEAKER NOTES — read or paraphrase in ~90 seconds

OPEN (10 sec)
"Our recommendation system helps Mirage decide which Rio-area corporate leads to call first. It is deliberately simple: rules and public data, not a black-box model — so the sales team can trust and adjust it."

WHAT IT DOES (20 sec)
"Each run can pull three kinds of signals: Portuguese news about office moves and expansions, optional enrichment from the company registry when we have a CNPJ, and public bid feeds when they mention office furniture. Everything is cached briefly so we do not hammer free APIs."

HOW SCORING WORKS (35 sec)
"Each lead gets three components. FIT asks: is this industry a strong match for high-end corporate furniture — tech, finance, legal, and similar sectors score highest. SIZE uses employee count or an estimate from registry data — bigger organizations get more points. URGENCY rewards recent news triggers — like a announced new headquarters — and multiplies by a small seasonal factor from regional economic data when enabled. We add the three parts into a total around thirty points and bucket into A, B, and C tiers. A means call now; B nurture; C monitor. Architects get a separate rank from past Mirage deals and momentum so we know whom to pair with top leads."

CLOSE (10 sec)
"The pipeline can run fully automated with APIs, or in a lightweight mode that only re-scores leads we already have. Output is sorted lists and exports for the monthly workflow."

Q&A hooks
- Why not AI? Transparency and cost; we can change weights without retraining.
- Data quality? Depends on NewsAPI key and CNPJ coverage; enrichment is best-effort.
"""


if __name__ == "__main__":
    main()
