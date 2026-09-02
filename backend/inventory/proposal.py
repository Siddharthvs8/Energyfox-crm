"""The customer's proposal: their figures, on the company's own artwork.

The document is designed, not coded — a cover photograph, a brand grid, a
schematic, six pages of terms. Recreating that in a PDF library would be a
worse-looking copy that drifts from the original every time the design changes.

So the approved template is uploaded per system type and its pages are used
verbatim. Only the three that carry a customer's own figures are touched, and
even those keep their background: the region that changes is painted over and
redrawn, so borders, logos and page numbers stay exactly where the designer put
them.

  page 1  the cover — who it is for, the system, the number and the date
  page 3  the specification table
  page 4  the price, and whether a subsidy applies

Everything else is passed through untouched.
"""
import logging
from decimal import Decimal
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)

# The rupee sign is the whole reason this is here: none of the fourteen fonts
# every PDF reader is guaranteed to have carries U+20B9, so an amount written in
# Helvetica comes out as "? 2,08,000" — which is what the customer would have
# received. DejaVu carries it, and is bundled rather than looked up on the
# machine so the document renders the same on a developer's laptop and on the
# server.
_FONT_FILE = Path(__file__).resolve().parent / 'fonts' / 'DejaVuSans-Bold.ttf'
MONEY_FONT = 'money'


def _register_money_font(page):
    """Make the rupee-capable font available on this page.

    Returns the name to draw with, or None when the file is missing — the
    caller then writes "Rs." instead. A missing font must cost the symbol, not
    the document.
    """
    try:
        page.insert_font(fontname=MONEY_FONT, fontfile=str(_FONT_FILE))
        return MONEY_FONT
    except Exception:
        logger.warning('Rupee font unavailable; amounts will read "Rs."')
        return None

# ── The template's own palette, read off the artwork ──
BLUE = (0 / 255, 74 / 255, 173 / 255)          # headings
DEEP_BLUE = (0.0, 0.2902, 0.6784)              # the filled header boxes
ORANGE = (248 / 255, 156 / 255, 28 / 255)      # the figures
GREY = (0.9765, 0.9725, 0.9725)                # the value boxes
WHITE = (1, 1, 1)
INK = (0.15, 0.16, 0.18)
RULE = (0.78, 0.80, 0.83)

# ── Where things sit, in the template's own coordinates (810 x 1012 pt) ──
COVER_TITLE = pymupdf.Rect(90, 200, 720, 275)
COVER_FIELDS = pymupdf.Rect(370, 706, 700, 840)   # the empty half of the table
COVER_META = pymupdf.Rect(138, 855, 480, 918)     # company / proposal no / date
# The label rows, read off the template: NAME 725-751, Phone NO 765-791,
# LOCATION 805-831. The value is written into the same band so it sits on the
# line with its label rather than floating above it.
COVER_ROWS = ((723, 753), (763, 793), (803, 833))

# Wide enough to take the template's own row separators with it: they start at
# x≈93, further left than the text does, and a narrower region left them
# sticking out beside the new rows like tick marks.
SPEC_TABLE = pymupdf.Rect(88, 186, 722, 690)      # under the Item/Brand/Quantity header
# The template's own column edges, counted off its cell rectangles — so the
# rows line up with the Item / Brand / Quantity header above them instead of
# sitting a few points inside it.
SPEC_COLS = (93, 301, 509, 718)                   # item | brand | quantity edges
# The template's own row height and body size, so a redrawn table sits in the
# page the way the designed one did.
SPEC_ROW_HEIGHT = 51
SPEC_FONT_SIZE = 16.5

PRICE_TITLE = pymupdf.Rect(90, 125, 720, 185)
PRICE_BAND = pymupdf.Rect(80, 200, 730, 330)
# The three columns as the designer placed them. The middle one is dead centre,
# which is what a single box uses when there is no subsidy to show.
PRICE_COLUMNS = ((89, 272), (314, 496), (538, 721))
BOX_HEADER_Y = (206, 264)
BOX_VALUE_Y = (264, 321)


def _rupees(amount, symbol='₹'):
    """Indian grouping, the way the template writes it: ₹ 3,35,000 /-"""
    n = int(Decimal(amount or 0).quantize(Decimal('1')))
    text = str(abs(n))
    if len(text) > 3:
        head, tail = text[:-3], text[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        text = ','.join(parts + [tail])
    return f"{'-' if n < 0 else ''}{symbol} {text} /-"


def _clear(page, *rects, words_only=False):
    """Take the template's own content out of these regions, properly.

    Painting a white rectangle over text only hides it: the words stay in the
    PDF's text layer, so a customer selecting the page — or any search — still
    finds the placeholder figures the template shipped with. Redaction removes
    the content itself, which for a document quoting somebody a price is the
    difference between a clean proposal and one carrying two sets of numbers.

    `words_only` decides how much else goes with them, and the two pages want
    opposite things:

      * The cover sits on a photograph and a diagonal colour band. Taking the
        artwork out with the text — or painting the region white afterwards —
        leaves a blank rectangle in the middle of the design. So there, only
        the words go.
      * The specification table and the pricing boxes sit on white, and their
        own cell shading and coloured panels have to go with the text, or the
        old stripes show through behind the new rows. There, everything in the
        region goes and the area is repainted clean.
    """
    for rect in rects:
        page.add_redact_annot(rect)
    if words_only:
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        return
    page.apply_redactions()
    for rect in rects:
        page.draw_rect(rect, color=None, fill=WHITE)


def _fit(page, rect, text, *, font, size, colour, align=pymupdf.TEXT_ALIGN_CENTER,
         min_size=7):
    """Write `text` into `rect`, shrinking until it fits.

    A customer's name is longer than the designer's placeholder more often than
    not, and a line that silently overflows is worse than a slightly smaller
    one — it lands on top of the artwork.
    """
    while size >= min_size:
        overflow = page.insert_textbox(rect, text, fontname=font, fontsize=size,
                                       color=colour, align=align)
        if overflow >= 0:
            return size
        size -= 0.5
    return size


def _cover(page, quotation):
    project = quotation.project
    lead = quotation.lead

    # The title is the project's own name — "5kW Single Phase On-Grid" — so the
    # cover says what was actually quoted rather than a size typed twice.
    title = (project.name if project else 'Solar Power System').upper()
    _clear(page, COVER_TITLE, COVER_META, words_only=True)
    _fit(page, COVER_TITLE + (0, 8, 0, 0), title,
         font='hebo', size=34, colour=BLUE)

    # The three empty cells of the customer table.
    name = (f"{lead.first_name or ''} {lead.last_name or ''}".strip() if lead else '')
    values = (name, (lead.phone if lead else '') or '', (quotation.site or
              (lead.installation_location or lead.company if lead else '') or ''))
    for (top, bottom), value in zip(COVER_ROWS, values):
        if not value:
            continue
        cell = pymupdf.Rect(COVER_FIELDS.x0 + 8, top, COVER_FIELDS.x1 - 8, bottom + 6)
        _fit(page, cell, str(value), font='hebo', size=16, colour=INK)

    # The number and the date beneath it.
    date = quotation.quotation_date
    meta = (f"ENERGYFOX CONSULTANTS PVT LTD\n"
            f"ProposalNo : {quotation.number}\n"
            f"Date : {date.strftime('%d.%m.%Y') if date else ''}")
    page.insert_textbox(COVER_META, meta, fontname='hebo', fontsize=13,
                        color=(0, 0, 0), align=pymupdf.TEXT_ALIGN_LEFT, lineheight=1.5)


def _specification(page, quotation):
    """Redraw the specification table from this quotation's own lines.

    Rows keep the template's own height rather than sharing out the space: a
    table of three lines stretched to fill the page looks nothing like the one
    the company designed, and the point of working on their artwork is that the
    result is theirs. The table simply ends after the last line.

    Only when there are more lines than the page has room for does the row
    height give way, down to what stays readable.
    """
    lines = list(quotation.spec_lines.all())
    _clear(page, SPEC_TABLE)
    if not lines:
        return

    top = SPEC_TABLE.y0 + 7
    available = SPEC_TABLE.y1 - top
    height = SPEC_ROW_HEIGHT
    if len(lines) * height > available:
        height = max(available / len(lines), 24)     # a long sheet tightens up
    size = SPEC_FONT_SIZE if height >= 44 else max(height * 0.32, 8)

    left, right = SPEC_COLS[0], SPEC_COLS[-1]
    y = top
    for line in lines:
        for (x0, x1), text in zip(zip(SPEC_COLS, SPEC_COLS[1:]),
                                  (line.item_name, line.brand or '-', line.quantity or '-')):
            _centred(page, pymupdf.Rect(x0, y, x1, y + height), str(text), size=size)
        y += height
        page.draw_line(pymupdf.Point(left, y), pymupdf.Point(right, y),
                       color=RULE, width=0.9)

    page.draw_rect(pymupdf.Rect(left, top, right, y), color=RULE, width=1.1)
    for x in SPEC_COLS[1:-1]:
        page.draw_line(pymupdf.Point(x, top), pymupdf.Point(x, y), color=RULE, width=1.1)


def _centred(page, cell, text, *, size):
    """Write `text` in the middle of `cell`, horizontally and vertically.

    insert_textbox starts at the top of the box, so a short line in a tall row
    sits against its upper border while the row below looks empty — which is
    what made the table read as a set of mismatched blocks rather than rows.
    The number of wrapped lines is measured first and the box nudged down by
    half of what is left over.
    """
    usable = cell.width - 12
    wrapped = 1
    if usable > 0:
        width = pymupdf.get_text_length(text, fontname='helv', fontsize=size)
        wrapped = max(1, int(width / usable) + (1 if width % usable else 0))
    leading = size * 1.25
    offset = max((cell.height - wrapped * leading) / 2, 1)
    box = pymupdf.Rect(cell.x0 + 6, cell.y0 + offset, cell.x1 - 6, cell.y1)
    _fit(page, box, text, font='helv', size=size, colour=INK)


def _pricing(page, quotation):
    """The price, and the subsidy only when one applies.

    A DCR system keeps the template's three boxes — what the customer pays, what
    the scheme returns, and the difference. A non-DCR system is not in the
    scheme at all, so it gets one box in the middle rather than a subsidy shown
    as zero, which would read as "you get nothing back" instead of "this system
    is not eligible".
    """
    project = quotation.project
    title = f"{project.name} Pricing" if project else 'Pricing'
    _clear(page, PRICE_TITLE, PRICE_BAND)
    money = _register_money_font(page)
    _fit(page, PRICE_TITLE + (0, 6, 0, 0), title, font='hebo', size=28, colour=BLUE)

    subsidy = quotation.subsidy_shown
    if subsidy:
        boxes = [('Amount to pay to\nEnergyfox', quotation.total, PRICE_COLUMNS[0]),
                 ('PM Surya Ghar\nsubsidy', subsidy, PRICE_COLUMNS[1]),
                 ('Net Effective price\nfor customer', quotation.net_effective,
                  PRICE_COLUMNS[2])]
    else:
        boxes = [('Amount to pay to\nEnergyfox', quotation.total, PRICE_COLUMNS[1])]

    for heading, amount, (x0, x1) in boxes:
        header = pymupdf.Rect(x0, BOX_HEADER_Y[0], x1, BOX_HEADER_Y[1])
        value = pymupdf.Rect(x0, BOX_VALUE_Y[0], x1, BOX_VALUE_Y[1])
        page.draw_rect(header, color=None, fill=DEEP_BLUE)
        page.draw_rect(value, color=RULE, fill=GREY, width=1)
        page.insert_textbox(header + (4, 9, -4, 0), heading, fontname='hebo',
                            fontsize=15, color=WHITE, align=pymupdf.TEXT_ALIGN_CENTER,
                            lineheight=1.35)
        # The bundled font where it is there, "Rs." where it is not.
        _fit(page, value + (4, 14, -4, 0),
             _rupees(amount, '₹' if money else 'Rs.'),
             font=money or 'hebo', size=23, colour=ORANGE)


def build_proposal(quotation, template_file):
    """The finished proposal, as PDF bytes.

    `template_file` is the uploaded artwork for this system type. Its pages come
    through untouched apart from the three that carry the customer's figures.
    """
    doc = pymupdf.open(stream=template_file.read(), filetype='pdf')
    try:
        # Guarded individually: a template with fewer pages than expected should
        # still produce the pages it does have rather than nothing at all.
        if doc.page_count >= 1:
            _cover(doc[0], quotation)
        if doc.page_count >= 3:
            _specification(doc[2], quotation)
        if doc.page_count >= 4:
            _pricing(doc[3], quotation)
        return doc.tobytes(deflate=True)
    finally:
        doc.close()
