"""Where the B2B invoice series stands. Read-only: it changes nothing.

    python manage.py invoice_series                 # this financial year
    python manage.py invoice_series --date 2027-04-02

Invoices run on from the last one on the books (see inventory.models
CONTINUOUS_SERIES), so the things worth knowing are: the highest invoice, the
numbers missing below it, and payments filed under a number that has no
invoice. Those payments are left behind when a delivery is deleted, or when
one was renamed before renaming carried its payments along (10 Oct 2026). The
series skips any number they sit under, so the new invoice cannot inherit
them — which leaves a gap when the series gets there.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_date

from inventory.models import DispatchPayment, StockDispatch, peek_document_number, series_key


def ranges(seqs):
    """[25, 26, 27, 30] -> '025-027, 030'."""
    out, run = [], []
    for s in sorted(seqs):
        if run and s == run[-1] + 1:
            run.append(s)
            continue
        if run:
            out.append(run)
        run = [s]
    if run:
        out.append(run)
    return ', '.join(f'{r[0]:03d}' if len(r) == 1 else f'{r[0]:03d}-{r[-1]:03d}' for r in out)


class Command(BaseCommand):
    help = 'Report on the B2B invoice series: highest invoice, gaps, stray payments, next number.'

    def add_arguments(self, parser):
        parser.add_argument('--date', help='Any day in the financial year to report on (default: today).')

    def handle(self, *args, **opts):
        on = parse_date(opts['date']) if opts.get('date') else timezone.localdate()
        if on is None:
            self.stderr.write('--date must look like 2026-10-14.')
            return
        key = series_key('IN', on)

        def seq_of(number):
            tail = str(number or '')[len(key):]
            return int(tail) if tail.isdigit() else None

        invoices = {}
        for d in (StockDispatch.objects.filter(invoice_no__startswith=key)
                  .select_related('customer').order_by('id')):
            s = seq_of(d.invoice_no)
            if s is not None:
                invoices.setdefault(s, d)

        stray = {}
        for p in DispatchPayment.objects.filter(invoice_no__startswith=key).order_by('paid_on', 'id'):
            s = seq_of(p.invoice_no)
            if s is not None and s not in invoices:
                stray.setdefault(s, []).append(p)

        write = self.stdout.write
        top = max(invoices, default=0)
        if top:
            write(f'Series {key}: {len(invoices)} invoice(s) on the books, highest {key}{top:03d}.')
        else:
            write(f'Series {key}: no invoices yet.')
        missing = [s for s in range(1, top + 1) if s not in invoices]
        if missing:
            write(f'Missing below it: {ranges(missing)}')
        write(f'Next invoice: {peek_document_number("IN", on=on)}')

        if stray:
            write('')
            write('Payments filed under a number with no invoice (the series skips these numbers):')
            for s in sorted(stray):
                payments = stray[s]
                total = sum((p.amount_received or Decimal('0') for p in payments), Decimal('0'))
                days = sorted({p.paid_on.isoformat() for p in payments if p.paid_on})
                modes = sorted({p.mode for p in payments})
                write(f'  {key}{s:03d}: {len(payments)} payment(s), Rs. {total:,.2f}, '
                      f'paid {", ".join(days) or "-"}, {"/".join(modes)}')
