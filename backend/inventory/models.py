from decimal import Decimal, ROUND_HALF_UP
from django.db import models


class Vendor(models.Model):
    """A supplier the workspace buys stock from."""
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150, blank=True, default='')
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, default='')
    gst_number = models.CharField(max_length=30, blank=True, default='')
    # Printed in the supplier block of a purchase order, beside the GST number.
    pan_number = models.CharField(max_length=20, blank=True, default='', verbose_name='PAN No')
    iec_code = models.CharField(max_length=30, blank=True, default='', verbose_name='IEC Code')
    payment_terms = models.CharField(max_length=100, blank=True, default='')
    address = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


# Domestic Content Requirement: the same system built with Indian-made modules
# rather than imported ones. It is a different price, not a different product,
# which is why a project quotes both and the invoice records which was chosen.
DCR, NON_DCR = 'dcr', 'non_dcr'
PRICE_VARIANTS = [(DCR, 'DCR'), (NON_DCR, 'Non-DCR')]

# How the system is wired. Module level because the project declares it and the
# proposal template is chosen by it, and one list keeps the two in step.
#
# Adding one here is most of the job: the project form, the template store and
# the proposal renderer all read this list. What a new type still needs is its
# own uploaded template — until then a quotation on it says so rather than
# sending the customer another system's document.
ON_GRID, HYBRID, MICRO_INVERTER, EN_PHASE = (
    'on_grid', 'hybrid', 'micro_inverter', 'en_phase')
SYSTEM_TYPES = [
    (ON_GRID, 'On-Grid'),
    (HYBRID, 'Hybrid'),
    (MICRO_INVERTER, 'Micro Inverter'),
    (EN_PHASE, 'EN-PHASE'),
]


def split_tax(amount, rate, inclusive):
    """Base, tax and total for an amount, told which side of the tax it sits on.

    The one place this arithmetic lives: a project quotes a price this way and a
    quotation totals itself the same way, and two copies of a tax calculation is
    how a document ends up disagreeing with the one it was made from.

    The tax is always the *difference* between total and base rather than its
    own rounded figure. Computed separately the two miss the total by a paisa on
    some numbers, and a document that does not add up is the first thing a
    customer notices.
    """
    amount = Decimal(amount or 0)
    rate = Decimal(rate or 0)
    if inclusive:
        # Taken out of the total rather than added to a base: the amount is the
        # number the customer was quoted and has to come back exactly.
        total = amount
        base = (amount / (Decimal('1') + rate / Decimal('100'))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)
    else:
        base = amount
        total = (amount + amount * rate / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {'amount': amount, 'base_amount': base,
            'tax_amount': total - base, 'total': total}


class _NumberedDoc(models.Model):
    """Shared header behaviour: auto document number + money math."""
    NUMBER_PREFIX = 'DOC'

    number = models.CharField(max_length=30, blank=True, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.number:
            self.number = f"{self.NUMBER_PREFIX}-{self.pk:04d}"
            super().save(update_fields=['number'])

    @property
    def subtotal(self):
        return sum((item.line_total for item in self.items.all()), Decimal('0'))

    def __str__(self):
        return self.number or f"{self.NUMBER_PREFIX} #{self.pk}"


# ─── Rounding ───────────────────────────────────────────────────────────────
RUPEE = Decimal('1')


def round_off_for(total):
    """A document total as whole rupees, and the adjustment that got it there.

    Invoices here are settled in cash, by cheque and over UPI, and nobody hands
    over 65 paise — so the customer is billed the round rupee and the invoice
    carries the difference as its own line, the way a printed tax invoice always
    has. Half a rupee rounds up, which is the convention every accountant here
    will check the figure against.

    Returns (grand_total, round_off): 95794.65 -> (95795, +0.35),
    153430.20 -> (153430, -0.20).
    """
    total = Decimal(total or 0)
    grand = total.quantize(RUPEE, rounding=ROUND_HALF_UP)
    return grand, grand - total


class RoundedTotalMixin:
    """`grand_total` and `round_off` for anything with a `total`.

    Kept apart from the total itself: `total` stays the exact arithmetic of the
    lines so the stock ledger and the tax figures still add up, and the rounding
    sits on top as its own visible line rather than quietly moving the maths.
    """

    @property
    def round_off(self):
        return round_off_for(self.total)[1]

    @property
    def grand_total(self):
        return round_off_for(self.total)[0]


class _TaxedDoc(RoundedTotalMixin, _NumberedDoc):
    """Header with discount + tax (Quotes & Sales Orders)."""
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta(_NumberedDoc.Meta):
        abstract = True

    @property
    def discount_amount(self):
        return (self.subtotal * (self.discount_percent or 0)) / Decimal('100')

    @property
    def taxable_amount(self):
        return self.subtotal - self.discount_amount

    @property
    def tax_amount(self):
        return (self.taxable_amount * (self.tax_percent or 0)) / Decimal('100')

    @property
    def total(self):
        return self.taxable_amount + self.tax_amount


# ─── Purchase Orders ────────────────────────────────────────────────────────
class PurchaseOrder(_NumberedDoc):
    NUMBER_PREFIX = 'PO'
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    order_date = models.DateField(null=True, blank=True)
    expected_date = models.DateField(null=True, blank=True)
    stock_received = models.BooleanField(default=False)  # guard: stock-in applied once

    @property
    def total(self):
        return self.subtotal


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('leads.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    description = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))


# ─── Proforma invoices ──────────────────────────────────────────────────────
def financial_year(on=None):
    """Indian FY label for a date: April–March, so 24 Jul 2026 → '26-27'."""
    from datetime import date
    d = on or date.today()
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


# ─── Wholesale document series ──────────────────────────────────────────────
# The B2B documents share one numbering scheme: REN<fy>-<kind><seq>, e.g.
# REN2627-PI001. Each kind counts on its own, and every series restarts at 001
# on 1 April because the financial-year code changes with it.
DOC_SERIES_PREFIX = 'REN'


def fy_code(on=None):
    """Financial year as the wholesale series writes it: 1 Apr 2026 → '2627'.

    Same April–March year as financial_year(), without the separator — the
    document numbers run the two halves together.
    """
    from datetime import date
    d = on or date.today()
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def series_key(kind, on=None):
    """The series a document of this kind and date belongs to, e.g. REN2627-PI."""
    return f"{DOC_SERIES_PREFIX}{fy_code(on)}-{kind}"


class DocumentNumberSeries(models.Model):
    """The high-water mark of an issued document series.

    A number, once issued, is spent: it has been on a document that went to a
    customer or a supplier, so it must never appear on a second one. Deleting
    the document does not release it — which is why the next number comes from
    a counter that only moves forward, rather than from counting the rows that
    happen to still exist.

    One row per series (REN2627-PI, REN2627-IN, REN2627-PO …), so 1 April opens
    a new counter and every series starts again at 001 on its own.
    """
    key = models.CharField(max_length=40, unique=True, db_index=True)
    last_seq = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']
        verbose_name_plural = 'Document number series'

    def __str__(self):
        return f"{self.key} — {self.last_seq} issued"

    @classmethod
    def issue(cls, key):
        """Take the next sequence in this series, under a row lock so two
        concurrent saves cannot be handed the same one."""
        from django.db import transaction
        with transaction.atomic():
            cls.objects.get_or_create(key=key)
            row = cls.objects.select_for_update().get(key=key)
            row.last_seq += 1
            row.save(update_fields=['last_seq', 'updated_at'])
            return row.last_seq

    @classmethod
    def peek(cls, key):
        """What issue() would return, without spending it."""
        row = cls.objects.filter(key=key).first()
        return (row.last_seq if row else 0) + 1

    @classmethod
    def absorb(cls, key, seq):
        """Move the counter up to `seq` if it is behind.

        A number can reach a document without passing through here — the dispatch
        form lets one be typed by hand, and imported paperwork carries its own.
        The counter never sees those, falls behind, and later hands out a number
        that is already on a customer's invoice. Absorbing a supplied number as
        it is saved is what stops that at the source.
        """
        from django.db import transaction
        with transaction.atomic():
            cls.objects.get_or_create(key=key)
            row = cls.objects.select_for_update().get(key=key)
            if seq > row.last_seq:
                row.last_seq = seq
                row.save(update_fields=['last_seq', 'updated_at'])
            return row.last_seq


# How to tell whether a number is already on a document, per series. The counter
# is the fast path; this is the backstop that makes a duplicate impossible even
# when the counter has drifted behind numbers it never issued.
def document_number_in_use(kind, number):
    from django.apps import apps
    model, field = {
        'IN': ('StockDispatch', 'invoice_no'),
        'PI': ('StockQuote', 'number'),
        'PO': ('StockPurchaseOrder', 'number'),
    }.get(kind, (None, None))
    if not model:
        return False
    return apps.get_model('inventory', model).objects.filter(**{field: number}).exists()


# A drifted counter is caught within a few steps; the bound is only here so a
# broken `in use` check can never spin forever.
_MAX_NUMBER_ATTEMPTS = 200


def next_document_number(kind, on=None):
    """Issue the next unused number in the REN<fy>-<kind><seq> series.

    Spends the number — call it only when a document is actually being created.

    Numbers already on a document are skipped rather than handed out again. The
    counter only moves forward, but it can still fall behind: a number typed by
    hand into the dispatch form never passes through it. Skipping what is taken
    means the series heals itself instead of colliding.
    """
    key = series_key(kind, on)
    for _ in range(_MAX_NUMBER_ATTEMPTS):
        candidate = f"{key}{DocumentNumberSeries.issue(key):03d}"
        if not document_number_in_use(kind, candidate):
            return candidate
    raise RuntimeError(f"Could not find a free number in the {key} series.")


def absorb_document_number(kind, number, on=None):
    """Teach the counter about a number that did not come from it."""
    key = series_key(kind, on)
    if not str(number or '').startswith(key):
        return                      # a different series (or year); not ours to move
    tail = str(number)[len(key):]
    if tail.isdigit():
        DocumentNumberSeries.absorb(key, int(tail))


def peek_document_number(kind, on=None):
    """The number the next document would take, without spending it."""
    key = series_key(kind, on)
    return f"{key}{DocumentNumberSeries.peek(key):03d}"


def next_proforma_number(on=None):
    """The next number in the EF/<FY>/PI<seq> series, e.g. EF/26-27/PI009.

    Retail and wholesale both raise proforma invoices, and the number is what the
    customer and the accountant key on — so the two share one series rather than
    each counting its own and minting duplicates. Numbers are probed rather than
    taken straight from a count, because deleting a document in the middle of the
    year would otherwise hand its successor's number out twice.
    """
    prefix = f"EF/{financial_year(on)}/PI"
    taken = set(
        list(Quote.objects.filter(number__startswith=prefix).values_list('number', flat=True))
        + list(StockQuote.objects.filter(number__startswith=prefix).values_list('number', flat=True))
    )
    n = len(taken) + 1
    while f"{prefix}{n:03d}" in taken:
        n += 1
    return f"{prefix}{n:03d}"


class _ProformaDoc(_TaxedDoc):
    """Shared behaviour for the two proforma invoice documents."""
    # Free-text reference printed on the invoice ("EFC Ref No.").
    efc_ref_no = models.CharField(max_length=60, blank=True, default='')
    # The generated PDF, kept so it can be emailed and linked to on WhatsApp.
    pdf = models.FileField(upload_to='proforma/', null=True, blank=True)
    # "Shipped to" overrides. Goods often go to a site that is not the customer's
    # registered address, so the delivery block is captured per invoice; blank
    # falls back to the customer's own details. `site` holds the address.
    ship_to_state = models.CharField(max_length=80, blank=True, default='')
    ship_to_gstin = models.CharField(max_length=20, blank=True, default='',
                                     verbose_name='Ship-to GSTIN')

    class Meta(_TaxedDoc.Meta):
        abstract = True

    @staticmethod
    def financial_year(on=None):
        return financial_year(on)

    def save(self, *args, **kwargs):
        creating = self._state.adding
        # Skip _NumberedDoc's simple QT-0001 numbering; this document has its own.
        models.Model.save(self, *args, **kwargs)
        if creating and not self.number:
            self.number = next_proforma_number(self.quote_date)
            models.Model.save(self, update_fields=['number'])


class Quote(_ProformaDoc):
    """The retail (B2C) proforma invoice, priced off the product catalogue."""
    NUMBER_PREFIX = 'PI'
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('converted', 'Converted'),
    ]
    lead = models.ForeignKey('leads.Lead', on_delete=models.SET_NULL, null=True, blank=True, related_name='quotes')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    quote_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    site = models.CharField(max_length=255, blank=True, default='')
    # Which project this proforma was built from. Kept for the record; the
    # specification actually quoted lives in `spec_lines`, which may since have
    # been edited away from it.
    project = models.ForeignKey('ProjectSpec', on_delete=models.SET_NULL, null=True,
                                blank=True, related_name='quotes')
    # Which of the project's two prices this invoice was written for. Recorded
    # on the document because "why is this quote ₹20,000 more than that one"
    # has exactly one answer and it should be on the paper.
    price_variant = models.CharField(max_length=8, choices=PRICE_VARIANTS, default=DCR)


class QuoteItem(models.Model):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('leads.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    description = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))


# ─── Projects (B2C product bundles) ─────────────────────────────────────────

class SpecLine(models.Model):
    """One line of a system specification: what it is, whose make, how many.

    Abstract because the same shape is kept three times — on the project, on the
    quotation, and on the proforma — and each keeps its own copy so that what
    was quoted cannot change because the project was edited afterwards.

    `quantity` is free text on purpose. The column in a real specification
    carries "1 Each", "36 M" and "50 Sqmm AL Conductor, Earth Pit, SS
    Mono-Spike" in neighbouring rows; a decimal and a unit could not hold the
    third. Nothing here is totalled or costed — this is a specification, not a
    price list — so there is nothing for a number to buy.
    """
    item_name = models.CharField(max_length=200)
    brand = models.CharField(max_length=200, blank=True, default='')
    quantity = models.CharField(max_length=120, blank=True, default='')
    # Sent by the client, so moving one line does not renumber the whole sheet.
    position = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ['position', 'id']

    def __str__(self):
        return self.item_name


class ProjectSpec(models.Model):
    """A named bundle of products — what the office calls a Project.

    Deliberately *not* named Project: ``leads.Project`` is already the
    installation stage a job passes through, and in code the two would be
    indistinguishable. This one is the specification a customer is sold — the
    panels, the inverter, the structure and the balance of system that make up
    one package — and it is what the B2C sidebar calls Project.

    It carries no prices. A proforma is still priced from its own line items;
    this is the sheet that says what the customer is getting.
    """
    name = models.CharField(max_length=200)
    # Blank is allowed rather than defaulted to On-Grid: the projects already on
    # the books were built before this field existed, and guessing their type
    # would put a wrong answer on a customer's quotation. An empty one simply
    # says nothing until someone sets it.
    system_type = models.CharField(max_length=20, choices=SYSTEM_TYPES,
                                   blank=True, default='', db_index=True)
    capacity = models.CharField(max_length=60, blank=True, default='',
                                help_text='e.g. 5kVA Single Phase')
    # What the package sells for. One figure per module type for the whole
    # project: the sheet below it is a specification, not a costed bill of
    # materials, and pricing each line would invite two totals for the same job.
    #
    # DCR and non-DCR are the same system built with differently sourced
    # modules, and they do not cost the same — so both are quoted here and the
    # invoice says which one it was written for.
    price_dcr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    price_non_dcr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # The PM Surya Ghar subsidy, which only a DCR system is eligible for — the
    # modules have to be Indian-made to qualify. It is not a discount the
    # company gives, so it never touches what the customer pays us; it is what
    # the government pays them back, and the proposal shows both figures and the
    # difference between them.
    subsidy_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # One rate and one inclusive/exclusive rule across both: it is the same sale
    # under the same tax, only the modules differ.
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Whether `price` is the final figure with tax already inside it, or the
    # base that tax is added to. Solar is quoted both ways and the difference is
    # the tax itself, so it is recorded rather than assumed.
    price_includes_tax = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')
    # Retired rather than deleted: a proforma issued last year still names the
    # project it was built from, and that record should not go blank.
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'project'
        verbose_name_plural = 'projects'

    def __str__(self):
        return self.name

    @property
    def full_name(self):
        """The project as it is named on a document: what it is, how it is
        wired, how big.

        One definition, because two documents name it — the invoice line and the
        printed quotation — and a customer holding both should not find the
        package described two different ways.
        """
        detail = ' — '.join(part for part in (self.get_system_type_display(),
                                              self.capacity) if part)
        return f'{self.name} — {detail}' if detail else self.name

    # ── What the customer pays ──
    # Derived, never stored: two copies of a total go out of step, and the one
    # on the screen is not always the one that was recalculated.
    def price_for(self, variant):
        return Decimal(
            (self.price_dcr if variant == DCR else self.price_non_dcr) or 0)

    def figures_for(self, variant):
        """Base, tax and total for one of the two prices."""
        figures = split_tax(self.price_for(variant), self.tax_percent,
                            self.price_includes_tax)
        return {'price': figures['amount'], **figures}

    def copy_onto(self, quote):
        """Stamp this project onto a proforma, replacing what was there.

        The one definition of what picking a project means: its specification
        and its price both come across. The copy is taken at this moment and
        belongs to the quote from here on — later changes to the project do not
        reach back into proformas already built from it, and editing a
        proforma does not reach forward into the project.
        """
        self.copy_spec_to(quote, QuoteSpecLine, 'quote')
        self.price_onto(quote)
    def copy_spec_to(self, doc, line_model, field):
        """Copy the specification onto any document that keeps one.

        Two documents now do — the quotation and the proforma — and they each
        get their own copy for the same reason: what was quoted must not change
        because the project was edited afterwards.
        """
        line_model.objects.filter(**{field: doc}).delete()
        line_model.objects.bulk_create([
            line_model(**{field: doc}, item_name=line.item_name,
                       brand=line.brand, quantity=line.quantity, position=line.position)
            for line in self.lines.all()
        ])

    def price_onto(self, quote):
        """Put the package on the invoice as its one priced line.

        Priced from whichever of the two the invoice is written for. The line
        carries `base_amount` with the project's rate on the document, so the
        proforma's own arithmetic — subtotal, discount, tax — lands on exactly
        the figure the project quotes; carrying a tax-inclusive price down as a
        line total instead would tax it twice.

        A project with no price for the chosen variant leaves the invoice alone:
        it is a specification that happens not to be priced that way, not an
        instruction to zero an invoice someone priced by hand.
        """
        from .models import QuoteItem      # defined below; imported at call time
        figures = self.figures_for(quote.price_variant)
        if not figures['price']:
            return
        label = dict(PRICE_VARIANTS)[quote.price_variant]
        quote.items.all().delete()
        QuoteItem.objects.create(
            quote=quote, description=f'{self.full_name} ({label})',
            quantity=Decimal('1'), unit_price=figures['base_amount'])
        quote.tax_percent = self.tax_percent
        quote.save(update_fields=['tax_percent'])


class ProjectSpecLine(SpecLine):
    project = models.ForeignKey(ProjectSpec, on_delete=models.CASCADE, related_name='lines')


class QuoteSpecLine(SpecLine):
    """The specification as it stands on one proforma.

    A copy, not a pointer into the project. Choosing a project fills these in;
    editing them afterwards changes this proforma and nothing else. One shared
    set of lines would mean tuning the specification for one customer silently
    rewrote every other quote built from the same project — including ones
    already sent — and a document a customer is holding must not change under
    them.
    """
    quote = models.ForeignKey('Quote', on_delete=models.CASCADE, related_name='spec_lines')


# ─── Quotations (B2C) ───────────────────────────────────────────────────────
def next_quotation_number(on=None):
    """The next number in the EF/<FY>/QT<seq> series, e.g. EF/26-27/QT009.

    Its own series, separate from the PI one the proforma invoices share: a
    quotation and the invoice it becomes are two documents the customer may hold
    at once, and giving them the same number would make them impossible to tell
    apart in a conversation.

    Numbers are probed rather than counted, for the same reason as the proforma
    series: deleting one mid-year would otherwise hand its successor's number
    out twice.
    """
    prefix = f"EF/{financial_year(on)}/QT"
    taken = set(Quotation.objects.filter(number__startswith=prefix)
                .values_list('number', flat=True))
    n = len(taken) + 1
    while f"{prefix}{n:03d}" in taken:
        n += 1
    return f"{prefix}{n:03d}"


class Quotation(RoundedTotalMixin, _NumberedDoc):
    """What the customer is offered, before any invoice is raised.

    Built from a project: the specification is copied across and the package
    price comes from whichever of the two prices the quotation is written for.
    From there it is negotiated — items edited, a discount given, extra costs
    added — and every one of those adjustments carries a remark, because "why is
    this ₹12,000 more than the list price" is asked months later by someone who
    was not in the room.

    The price fields are copied from the project rather than read through it, so
    a quotation already sent cannot change because someone edited the project
    afterwards.
    """
    NUMBER_PREFIX = 'QT'
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('converted', 'Converted'),
    ]

    lead = models.ForeignKey('leads.Lead', on_delete=models.SET_NULL, null=True,
                             blank=True, related_name='quotations')
    project = models.ForeignKey('ProjectSpec', on_delete=models.SET_NULL, null=True,
                                blank=True, related_name='quotations')
    price_variant = models.CharField(max_length=8, choices=PRICE_VARIANTS, default=DCR)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft',
                              db_index=True)
    quotation_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    site = models.CharField(max_length=255, blank=True, default='')

    # Copied from the project when one is chosen, then the desk's to change.
    package_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    price_includes_tax = models.BooleanField(default=False)

    # A flat amount off, never a percentage: a discount is agreed in rupees
    # across a table, and reverse-engineering the percentage that produced it
    # only introduces a rounding error into a number two people shook on.
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_remark = models.CharField(max_length=255, blank=True, default='')

    # Copied from the project, then the desk's to change: the scheme's slabs
    # move, and a customer's eligibility is settled with them, not with us.
    subsidy_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # The proforma this became, if it was accepted.
    converted_quote = models.ForeignKey('Quote', on_delete=models.SET_NULL, null=True,
                                        blank=True, related_name='source_quotation')
    # The rendered document, kept so email can attach it, WhatsApp can link to
    # it, and the lead's own page can offer it for download later. Same
    # arrangement as the proforma invoice — see deliver_document.
    pdf = models.FileField(upload_to='quotations/', null=True, blank=True)

    class Meta(_NumberedDoc.Meta):
        pass

    def save(self, *args, **kwargs):
        creating = self._state.adding
        # Skip _NumberedDoc's QT-0001 numbering; this document has its own series.
        models.Model.save(self, *args, **kwargs)
        if creating and not self.number:
            self.number = next_quotation_number(self.quotation_date)
            models.Model.save(self, update_fields=['number'])

    # ── What it comes to ──
    @property
    def extras_total(self):
        return sum((c.amount or Decimal('0') for c in self.costs.all()), Decimal('0'))

    @property
    def subtotal(self):
        """The package plus whatever was added to it, before the discount.

        Overrides _NumberedDoc.subtotal, which sums line items; a quotation is
        one package and a list of extras, not a list of products.
        """
        return Decimal(self.package_amount or 0) + self.extras_total

    @property
    def net_amount(self):
        """What is left after the discount — the figure tax is worked on."""
        return self.subtotal - Decimal(self.discount_amount or 0)

    @property
    def figures(self):
        """Base, tax and total, on the same side of the tax as the package price.

        If the project quoted a tax-inclusive price then the extras and the
        discount are inclusive too, because they are adjustments to that same
        figure. Mixing the two sides on one document is how a quotation ends up
        a few thousand rupees away from what anybody agreed.
        """
        return split_tax(self.net_amount, self.tax_percent, self.price_includes_tax)

    @property
    def total(self):
        return self.figures['total']

    @property
    def subsidy_shown(self):
        """The subsidy this quotation may show — nothing, unless it is DCR.

        Only Indian-made modules qualify for PM Surya Ghar, so a non-DCR
        proposal carries no subsidy box at all. Printing one at zero would read
        as "you get nothing back", which is a different claim from "this system
        is not in the scheme".
        """
        return Decimal(self.subsidy_amount or 0) if self.price_variant == DCR else Decimal('0')

    @property
    def net_effective(self):
        """What the customer is out of pocket once the subsidy reaches them."""
        return self.total - self.subsidy_shown

    def fill_from_project(self):
        """Take the specification and the price from the chosen project.

        The one definition of what picking a project on a quotation means. A
        project priced at nothing for the chosen variant leaves the amount
        alone, the same rule the proforma follows.
        """
        if not self.project_id:
            return
        project = self.project
        project.copy_spec_to(self, QuotationSpecLine, 'quotation')
        figures = project.figures_for(self.price_variant)
        if figures['price']:
            self.package_amount = figures['price']
        self.tax_percent = project.tax_percent
        self.price_includes_tax = project.price_includes_tax
        self.subsidy_amount = project.subsidy_amount
        self.save(update_fields=['package_amount', 'tax_percent', 'price_includes_tax',
                                 'subsidy_amount', 'updated_at'])


class QuotationTemplate(models.Model):
    """The branded proposal document, per system type.

    Uploaded rather than drawn in code: it is a designed document — cover
    photograph, brand grid, schematic, terms — and the pages that do not change
    are taken from it verbatim so the customer receives exactly the artwork the
    company approved. Only the pages that carry the customer's own figures are
    redrawn. See `proposal.py`.
    """
    system_type = models.CharField(max_length=20, choices=SYSTEM_TYPES, unique=True)
    pdf = models.FileField(upload_to='quotation-templates/')
    uploaded_at = models.DateTimeField(auto_now=True)
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name='+')

    class Meta:
        ordering = ['system_type']

    def __str__(self):
        return f'{self.get_system_type_display()} proposal template'


class QuotationSpecLine(SpecLine):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE,
                                  related_name='spec_lines')


class QuotationCost(models.Model):
    """One thing added to the price, and why.

    The remark is not optional decoration. A crane, a longer cable run and a
    scaffold are three different conversations with the customer, and a single
    lump labelled "extra charges" is the one a customer argues with.
    """
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='costs')
    remark = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return f'{self.remark} — {self.amount}'


# ─── Sales Orders ───────────────────────────────────────────────────────────
class SalesOrder(_TaxedDoc):
    NUMBER_PREFIX = 'SO'
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    lead = models.ForeignKey('leads.Lead', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_orders')
    source_quote = models.ForeignKey(Quote, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    order_date = models.DateField(null=True, blank=True)
    stock_committed = models.BooleanField(default=False)  # guard: stock-out applied once


class SalesOrderItem(models.Model):
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('leads.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    description = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))


# ─── Stock register ─────────────────────────────────────────────────────────
# A warehouse-side stock ledger, separate from the sales documents above. Every
# figure is derived rather than stored, so the books can never drift from the
# facts that made them:
#
#   physical_stock = opening + goods received − dispatched   (what is on the shelf)
#   reserved       = live proforma lines                     (what is promised)
#   closing_stock  = physical_stock − reserved               (what is left to sell)

# Proforma statuses that hold stock back. A converted one is left out because
# its dispatch rows have already taken the goods off the shelf — counting both
# would remove the same units twice. A declined one is left out because the
# offer is off and the goods are free again.
LIVE_QUOTE_STATUSES = ('draft', 'sent', 'accepted')


class StockItem(models.Model):
    """One SKU in the warehouse — a panel, inverter, battery, structure, cable."""
    CATEGORY_CHOICES = [
        ('Solar Panel', 'Solar Panel'),
        ('Inverter', 'Inverter'),
        ('Battery', 'Battery'),
        ('Mounting Structure', 'Mounting Structure'),
        ('Cable', 'Cable'),
        ('BOS Accessory', 'BOS Accessory'),
        ('Other', 'Other'),
    ]

    code = models.CharField(max_length=40, unique=True)
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES, default='Other', db_index=True)
    hsn = models.CharField(max_length=20, blank=True, default='', verbose_name='HSN / SAC',
                           help_text='Printed against this item on the proforma invoice')
    brand = models.CharField(max_length=120, blank=True, default='')
    model_name = models.CharField(max_length=150, blank=True, default='', verbose_name='Model / spec')
    unit = models.CharField(max_length=20, default='Nos')

    opening_stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    location = models.CharField(max_length=150, blank=True, default='')

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return self.code

    # Fall back to per-row queries when the row wasn't annotated by the viewset.
    @property
    def received(self):
        cached = getattr(self, 'received_qty', None)
        if cached is not None:
            return cached
        return self.receipts.aggregate(t=models.Sum('quantity'))['t'] or Decimal('0')

    @property
    def dispatched(self):
        """Units that have actually left. A pending dispatch has not shipped, so
        it reserves rather than moves — see `reserved`."""
        cached = getattr(self, 'dispatched_qty', None)
        if cached is not None:
            return cached
        return (self.dispatches.filter(status=StockDispatch.RELEASED)
                .aggregate(t=models.Sum('quantity'))['t'] or Decimal('0'))

    @property
    def reserved(self):
        """Units promised but not yet gone: live proforma lines, plus dispatches
        raised and waiting on payment.

        Held rather than moved: the goods are still on the shelf, but they are
        spoken for, so they must not be offered to a second customer. The figure
        is summed from those documents rather than stored, which is what makes it
        release itself — delete the proforma, decline it, or release the dispatch,
        and the stock follows with nothing to unwind.
        """
        cached = getattr(self, 'reserved_qty', None)
        if cached is not None:
            return cached
        on_quotes = (self.quote_lines.filter(quote__status__in=LIVE_QUOTE_STATUSES)
                     .aggregate(t=models.Sum('quantity'))['t'] or Decimal('0'))
        on_dispatches = (self.dispatches.filter(status=StockDispatch.PENDING)
                         .aggregate(t=models.Sum('quantity'))['t'] or Decimal('0'))
        return on_quotes + on_dispatches

    @property
    def physical_stock(self):
        """What is actually in the warehouse: opening, plus what came in, less
        what went out. Reserved units are still here — promised, not gone — so
        this is the figure the stock is *valued* at."""
        return (self.opening_stock or Decimal('0')) + self.received - self.dispatched

    @property
    def closing_stock(self):
        """What is left to sell: the shelf, less what proforma invoices have
        already promised.

        Deliberately net of reservations rather than the raw ledger figure,
        because this is the number every screen quotes — and a stock count that
        includes goods already promised to someone else is how the same panel
        gets sold twice. `physical_stock` is the raw figure for anyone who needs
        it.
        """
        return self.physical_stock - self.reserved

    @property
    def stock_value(self):
        # Valued on what is owned, not on what is free to sell: a reserved panel
        # is still the company's until it is dispatched and paid for.
        return self.physical_stock * (self.unit_cost or Decimal('0'))

    @property
    def needs_reorder(self):
        # Against what can still be sold. An item whose whole shelf is promised
        # away needs restocking just as much as an empty one.
        return self.closing_stock <= (self.reorder_level or Decimal('0'))


class StockCustomer(models.Model):
    """A buyer / project site the warehouse dispatches to."""
    name = models.CharField(max_length=200)
    gstin = models.CharField(max_length=30, blank=True, default='')
    contact_person = models.CharField(max_length=150, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    site_address = models.CharField(max_length=255, blank=True, default='')
    state = models.CharField(max_length=80, blank=True, default='')
    contact_number = models.CharField(max_length=20, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class _StockMovement(models.Model):
    """Shared shape of an inward/outward line: which item, how many, at what rate."""
    date = models.DateField(db_index=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-date', '-id']

    @property
    def amount(self):
        return (self.quantity or Decimal('0')) * (self.rate or Decimal('0'))


class GoodsReceipt(_StockMovement):
    """Stock in — a GRN against a supplier."""
    grn_no = models.CharField(max_length=30, blank=True, default='', db_index=True)
    supplier = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='goods_receipts')
    # PROTECT: an item with movement history can't be deleted out from under it.
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='receipts')

    def __str__(self):
        return self.grn_no or f"GRN #{self.pk}"


class StockDispatch(_StockMovement):
    """Stock out — a delivery to a customer / project site.

    A dispatch is raised before it ships. While it is `pending` the goods are
    still in the warehouse — spoken for, but not gone — so it *reserves* stock
    rather than moving it, exactly as a live proforma does. Releasing it is what
    takes the goods off the shelf, and that needs the invoice settled in full.
    """
    PENDING, RELEASED = 'pending', 'released'
    STATUS_CHOICES = [(PENDING, 'Pending payment'), (RELEASED, 'Released')]

    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default=RELEASED, db_index=True)
    released_at = models.DateTimeField(null=True, blank=True)
    invoice_no = models.CharField(max_length=30, blank=True, default='', db_index=True)
    customer = models.ForeignKey(StockCustomer, on_delete=models.SET_NULL, null=True, blank=True, related_name='dispatches')
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='dispatches')
    site = models.CharField(max_length=255, blank=True, default='')
    # GST on the line. `amount` stays the pre-tax figure so the stock ledger keeps
    # valuing movements at their goods value; `total` is what the customer pays.
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Serials of the units that went out on this line, printed on the invoice.
    # Free text so a range ("SN001-SN010") reads as well as a list.
    serial_numbers = models.TextField(blank=True, default='')
    # The generated invoice, kept so it can be emailed and linked to on WhatsApp.
    # A dispatch document is the set of rows sharing an invoice_no; the file is
    # stored against the first of them.
    pdf = models.FileField(upload_to='invoices/', null=True, blank=True)

    class Meta(_StockMovement.Meta):
        verbose_name_plural = 'Stock dispatches'

    def save(self, *args, **kwargs):
        # A delivery of several products is several rows sharing one invoice
        # number, so only a row that arrives without one mints it — the client
        # sends the number it got back on the rest of the set.
        if self._state.adding:
            if not self.invoice_no:
                self.invoice_no = next_document_number('IN', on=self.date)
            else:
                # Typed by hand, or carried over from the set: tell the counter,
                # so the series cannot issue this number to someone else later.
                absorb_document_number('IN', self.invoice_no, on=self.date)
        super().save(*args, **kwargs)

    @property
    def tax_amount(self):
        return (self.amount * (self.tax_percent or Decimal('0'))) / Decimal('100')

    @property
    def total(self):
        return self.amount + self.tax_amount

    def __str__(self):
        return self.invoice_no or f"Dispatch #{self.pk}"


class DispatchPayment(models.Model):
    """One verified payment against a document, in instalments if need be.

    Verifying and dispatching are two separate acts: money can be taken and
    checked in parts, and the goods go out only once the whole invoice has been
    settled. So this is one row *per payment*, not one per document — a delivery
    paid half in cash and half by transfer has two of them.

    It attaches to whichever document the customer is paying against: a proforma
    invoice before there is a delivery, or a pending dispatch raised directly.
    Exactly one of the two is set.
    """
    MODE_CHOICES = [
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('bank', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('card', 'Card'),
        # Goods released on agreed terms. It counts towards settling the invoice
        # — that is the whole point of recording it — while still standing in the
        # ledger as what it is, so a credit sale can be told from a paid one.
        ('credit', 'Credit'),
    ]
    # The dispatch this pays for, by its invoice number: a delivery of several
    # products is several StockDispatch rows sharing one, and the customer pays
    # for the delivery rather than a row of it.
    invoice_no = models.CharField(max_length=30, blank=True, default='', db_index=True)
    quote = models.ForeignKey('StockQuote', on_delete=models.CASCADE, null=True, blank=True,
                              related_name='payments')
    # What was owed when this payment was taken, stored beside what was taken.
    # Editing a line afterwards changes the document; it must not be able to
    # rewrite the history of what was actually verified.
    invoice_total = models.DecimalField(max_digits=14, decimal_places=2)
    amount_received = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    # UTR / cheque number / transaction id — whatever proves the money arrived.
    reference = models.CharField(max_length=100, blank=True, default='')
    paid_on = models.DateField()
    notes = models.TextField(blank=True, default='')
    verified_by = models.ForeignKey('users.User', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='+')
    verified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['verified_at', 'id']
        constraints = [
            models.CheckConstraint(
                check=(models.Q(quote__isnull=False, invoice_no='')
                       | models.Q(quote__isnull=True) & ~models.Q(invoice_no='')),
                name='payment_belongs_to_one_document',
            ),
        ]

    def __str__(self):
        return f"{self.invoice_no or self.quote_id} — {self.amount_received}"

    @staticmethod
    def received_for(*, quote=None, invoice_no=None):
        """What has been verified against a document so far.

        Credit counts: it is a way of settling the invoice, not a note beside it.
        """
        rows = (DispatchPayment.objects.filter(quote=quote) if quote is not None
                else DispatchPayment.objects.filter(invoice_no=invoice_no))
        return rows.aggregate(t=models.Sum('amount_received'))['t'] or Decimal('0')


class StockQuote(_ProformaDoc):
    """A wholesale proforma invoice over stock items.

    Reuses the same header maths as the retail Quote (subtotal → discount → tax),
    but priced off StockItem rather than the product catalogue. Accepting one is
    recorded by converting it, which writes the dispatch rows that take the goods
    out of stock — see StockQuoteViewSet.convert.

    Numbered in the wholesale series — REN<fy>-PI<seq>, e.g. REN2627-PI001 —
    which restarts each Indian financial year (April–March).
    """
    NUMBER_PREFIX = 'PI'
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('converted', 'Converted'),
    ]
    customer = models.ForeignKey(StockCustomer, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='quotes')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    quote_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    site = models.CharField(max_length=255, blank=True, default='')
    # Guard: a quote's stock may only be dispatched once.
    converted_at = models.DateTimeField(null=True, blank=True)

    class Meta(_ProformaDoc.Meta):
        constraints = [
            models.UniqueConstraint(fields=['number'], name='uniq_stock_quote_number'),
        ]

    def save(self, *args, **kwargs):
        # The wholesale series, not the retail EF/<fy>/PI one the base assigns.
        creating = self._state.adding
        models.Model.save(self, *args, **kwargs)
        if creating and not self.number:
            self.number = next_document_number('PI', on=self.quote_date)
            models.Model.save(self, update_fields=['number'])


class StockQuoteItem(models.Model):
    quote = models.ForeignKey(StockQuote, on_delete=models.CASCADE, related_name='items')
    # PROTECT for the same reason movements use it: an item with paperwork against
    # it can't be deleted out from under it.
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='quote_lines')
    description = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))


# ─── Purchase orders (wholesale) ────────────────────────────────────────────
def next_stock_po_number(on=None):
    """The number the next purchase order would take, e.g. REN2627-PO001.

    A preview for the form — it does not spend the number.
    """
    return peek_document_number('PO', on=on)


class StockPurchaseOrder(models.Model):
    """An order raised on a supplier for stock — the paperwork that goes out
    before the goods arrive, which the GRN then receives against.

    The printed form is the company's own purchase-order template: supplier
    block, bill-to / ship-to, the spares table, a transportation charge, and one
    tax rate applied to the whole order.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    # The wholesale series number, e.g. REN2627-PO001. 'fy' is kept alongside it
    # for filtering; the year is embedded in the number too.
    number = models.CharField(max_length=30, blank=True, db_index=True)
    fy = models.CharField(max_length=10, blank=True, db_index=True)
    po_date = models.DateField(null=True, blank=True)
    supplier = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='stock_purchase_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)

    # Ship-to is per order: stock often goes to a site rather than the office.
    # Blank falls back to the company's own address on the printed form.
    ship_to_address = models.TextField(blank=True, default='')
    ship_to_phone = models.CharField(max_length=40, blank=True, default='')

    # Freight is charged on the order, not against any one line, and it is taxed
    # with the goods — so it sits between the line table and the tax row.
    transportation = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    # IGST for an inter-state supplier, CGST+SGST within the state. Printed as
    # entered so the document matches whichever applies.
    tax_label = models.CharField(max_length=20, blank=True, default='IGST')

    terms_taxes = models.CharField(max_length=255, blank=True, default='As Mentioned')
    terms_delivery = models.CharField(max_length=255, blank=True, default='Immediately')
    notes = models.TextField(blank=True, default='')

    # The generated PDF, kept so it can be emailed and linked to on WhatsApp.
    pdf = models.FileField(upload_to='purchase-orders/', null=True, blank=True)

    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['fy', 'number'], name='uniq_stock_po_number_per_fy'),
        ]

    def __str__(self):
        return f"PO {self.number}/{self.fy}" if self.number else f"PO #{self.pk}"

    def save(self, *args, **kwargs):
        if not self.fy:
            self.fy = financial_year(self.po_date)
        if not self.number:
            self.number = next_document_number('PO', on=self.po_date)
        super().save(*args, **kwargs)

    # ── Money. Freight is part of the taxable value, as the template shows. ──
    @property
    def goods_amount(self):
        return sum((li.base_amount for li in self.items.all()), Decimal('0'))

    @property
    def taxable_amount(self):
        return self.goods_amount + (self.transportation or Decimal('0'))

    @property
    def tax_amount(self):
        return self.taxable_amount * (self.tax_percent or Decimal('0')) / Decimal('100')

    @property
    def total(self):
        return self.taxable_amount + self.tax_amount


class StockPurchaseOrderItem(models.Model):
    """One line of the spares table."""
    purchase_order = models.ForeignKey(StockPurchaseOrder, on_delete=models.CASCADE, related_name='items')
    # Optional: an order may be raised for a catalogued item or for a one-off
    # spare that has no stock record yet. PROTECT matches the movement tables.
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, null=True, blank=True,
                             related_name='purchase_order_lines')
    type_of_spare = models.CharField(max_length=120, blank=True, default='')
    description = models.CharField(max_length=255, blank=True, default='')
    part_code = models.CharField(max_length=80, blank=True, default='')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)

    class Meta:
        ordering = ['id']

    @property
    def base_amount(self):
        return (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))
