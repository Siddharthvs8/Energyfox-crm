"""Money-receipt (voucher) helpers: financial year, amount-in-words (Indian
numbering) and issuing a sequential ReceiptVoucher for a payment."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone


def indian_financial_year(d):
    """Return the FY label for a date, e.g. 2026-07-16 -> '26-27'.
    India's financial year runs April 1 – March 31."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


_ONES = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
         'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
         'Seventeen', 'Eighteen', 'Nineteen']
_TENS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']


def _two_digits(n):
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (' ' + _ONES[n % 10] if n % 10 else '')).strip()


def _three_digits(n):
    """0–999 in words."""
    out = ''
    if n >= 100:
        out += _ONES[n // 100] + ' Hundred'
        n %= 100
        if n:
            out += ' '
    if n:
        out += _two_digits(n)
    return out


def amount_in_words(amount):
    """Indian-numbering rupee words, e.g. 500000 -> 'Rupees Five Lakh Only'.
    Paise, if any, are appended (e.g. '… and Fifty Paise')."""
    amount = Decimal(str(amount or 0))
    rupees = int(amount)
    paise = int((amount - rupees) * 100 + Decimal('0.5'))

    if rupees == 0:
        words = 'Zero'
    else:
        crore = rupees // 10000000
        rupees %= 10000000
        lakh = rupees // 100000
        rupees %= 100000
        thousand = rupees // 1000
        hundreds = rupees % 1000
        parts = []
        if crore:
            parts.append(_three_digits(crore) + ' Crore')
        if lakh:
            parts.append(_three_digits(lakh) + ' Lakh')
        if thousand:
            parts.append(_three_digits(thousand) + ' Thousand')
        if hundreds:
            parts.append(_three_digits(hundreds))
        words = ' '.join(parts)

    result = f'Rupees {words} Only'
    if paise:
        result = f'Rupees {words} and {_two_digits(paise)} Paise Only'
    return result


def issue_receipt(lead, amount, *, on_account_of='', payment_mode='',
                  balance_payment=None, is_initial=False, created_by=None):
    """Create a sequential ReceiptVoucher for a payment (idempotent for a given
    balance payment — one receipt per payment row)."""
    from .models import ReceiptVoucher

    if amount is None or Decimal(str(amount)) <= 0:
        return None

    if balance_payment is not None:
        existing = ReceiptVoucher.objects.filter(balance_payment=balance_payment).first()
        if existing:
            return existing
    if is_initial:
        existing = ReceiptVoucher.objects.filter(lead=lead, is_initial=True).first()
        if existing:
            return existing

    today = timezone.localdate()
    fy = indian_financial_year(today)
    name = f"{lead.first_name} {lead.last_name or ''}".strip()
    address = lead.installation_location or lead.company or ''

    # Allocate the next sequence for this FY under a row lock so two concurrent
    # payments can't grab the same number.
    with transaction.atomic():
        last = (ReceiptVoucher.objects.select_for_update()
                .filter(fy=fy).order_by('-seq').first())
        seq = (last.seq + 1) if last else 1
        return ReceiptVoucher.objects.create(
            lead=lead, balance_payment=balance_payment, is_initial=is_initial,
            number=f"ER/{fy}/{seq:03d}", fy=fy, seq=seq,
            date=today, amount=amount, amount_in_words=amount_in_words(amount),
            on_account_of=on_account_of or '', payment_mode=payment_mode or '',
            received_from=name, address=address, created_by=created_by,
        )
