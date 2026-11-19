"""Raising and editing a quotation lands on its customer's Activity Timeline.

The timeline is where a customer's file is read — by accounts, by the project
team, by a manager asking why a figure moved — and a quotation is the price put
in front of that customer. So both are recorded under whoever did them, and an
edit says what it changed rather than only that something did.
"""
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from leads.models import ActivityLog, Lead
from users.models import User
from .models import Quotation


def token_for(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


def mk(username, role, first_name):
    u = User.objects.create_user(username=username, password='Pw@123456',
                                 first_name=first_name)
    u.role = role
    u.save()
    return u


class QuotationTimelineTests(TestCase):
    def setUp(self):
        self.admin = mk('qt_admin', 'superadmin', 'Asha')
        self.bde = mk('qt_bde', 'bde', 'Bibin')
        self.lead = Lead.objects.create(first_name='Ravi', last_name='Kumar', phone='9990011001',
                                        assigned_to=self.bde, bde=self.bde)
        r = self.send('post', '/api/projects/', {
            'name': '5kW On-Grid', 'price_dcr': '200000', 'price_non_dcr': '180000',
            'tax_percent': '18', 'price_includes_tax': True,
            'lines': [
                {'item_name': 'Topcon-Adani', 'brand': '', 'quantity': '10 Nos', 'position': 0},
                {'item_name': 'DC Cable', 'brand': 'POLYCAB', 'quantity': '36 M', 'position': 1},
            ]})
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.project = r.json()

    # ── Helpers ──
    def send(self, method, url, body, user=None):
        return getattr(self.client, method)(
            url, data=body, content_type='application/json',
            HTTP_AUTHORIZATION=token_for(user or self.admin))

    def get(self, url):
        r = self.client.get(url, HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def raise_quotation(self, user=None, **fields):
        body = {'lead': self.lead.id, 'project': self.project['id'],
                'quotation_date': '2026-09-01', **fields}
        r = self.send('post', '/api/quotations/', body, user)
        self.assertEqual(r.status_code, 201, r.content[:300])
        # Re-read the way the edit form loads it.
        return self.get(f"/api/quotations/{r.json()['id']}/")

    def edit(self, q, user=None, **changes):
        """Save the way the edit form does: every field, as it was loaded, with
        the user's changes on top."""
        body = {k: q[k] for k in (
            'lead', 'project', 'price_variant', 'status', 'quotation_date', 'expiry_date',
            'site', 'package_amount', 'tax_percent', 'price_includes_tax', 'subsidy_amount',
            'discount_amount', 'discount_remark', 'notes')}
        body['spec_lines'] = [{**l, 'position': i} for i, l in enumerate(q['spec_lines'])]
        body['costs'] = [{**c, 'position': i} for i, c in enumerate(q['costs'])]
        body.update(changes)
        return self.send('patch', f"/api/quotations/{q['id']}/", body, user)

    def entries(self, kind, lead=None):
        """This customer's timeline entries of one kind, as the timeline serves them."""
        timeline = self.get(f'/api/leads/{(lead or self.lead).id}/activity-timeline/')
        return [e for e in timeline['entries'] if e['type'] == kind]

    # ── Raising one ──
    def test_raising_a_quotation_is_recorded_under_whoever_raised_it(self):
        q = self.raise_quotation(user=self.bde)
        [entry] = self.entries('quotation_created')
        self.assertEqual(entry['description'],
                         f"Quotation {q['number']} created — 5kW On-Grid (DCR), ₹2,00,000.")
        self.assertEqual(entry['actor'], 'Bibin')
        self.assertFalse(entry['auto_generated'])

    def test_a_discount_is_named_with_its_reason(self):
        q = self.raise_quotation(discount_amount='15000', discount_remark='Repeat customer')
        [entry] = self.entries('quotation_created')
        self.assertEqual(entry['description'],
                         f"Quotation {q['number']} created — 5kW On-Grid (DCR), ₹1,85,000 "
                         f"after a ₹15,000 discount (Repeat customer).")

    def test_one_raised_without_a_customer_has_no_timeline_to_go_on(self):
        before = ActivityLog.objects.count()
        self.raise_quotation(lead=None)
        self.assertEqual(ActivityLog.objects.count(), before)

    def test_the_lead_page_timeline_shows_it_too(self):
        """The lead's own page reads /history/, not /activity-timeline/."""
        q = self.raise_quotation()
        history = self.get(f'/api/leads/{self.lead.id}/history/')
        self.assertIn(('quotation_created', q['number']),
                      [(h['type'], (h['extra'] or {}).get('number')) for h in history])

    # ── Editing one ──
    def test_an_edit_says_what_it_changed(self):
        q = self.raise_quotation()
        r = self.edit(q, user=self.bde, status='accepted',
                      discount_amount='15000', discount_remark='Repeat customer')
        self.assertEqual(r.status_code, 200, r.content[:300])
        [entry] = self.entries('quotation_edited')
        self.assertEqual(entry['description'],
                         f"Quotation {q['number']} edited — Status: Draft → Accepted; "
                         f"Discount: ₹0 → ₹15,000; Discount reason: — → Repeat customer; "
                         f"Total: ₹2,00,000 → ₹1,85,000.")
        self.assertEqual(entry['actor'], 'Bibin')

    def test_saving_without_changing_anything_is_not_an_edit(self):
        q = self.raise_quotation(discount_amount='15000', discount_remark='Repeat customer',
                                 costs=[{'remark': 'Crane hire', 'amount': '12000', 'position': 0}])
        r = self.edit(q)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.entries('quotation_edited'), [])

    def test_the_specification_and_the_extra_costs_are_reported(self):
        q = self.raise_quotation()
        more = q['spec_lines'] + [{'item_name': 'Earthing kit', 'brand': '', 'quantity': '1 Set'}]
        self.edit(q, spec_lines=[{**l, 'position': i} for i, l in enumerate(more)],
                  costs=[{'remark': 'Crane hire', 'amount': '12000', 'position': 0}])
        [entry] = self.entries('quotation_edited')
        self.assertEqual(entry['description'],
                         f"Quotation {q['number']} edited — Specifications: 2 items → 3 items; "
                         f"Additional costs: ₹0 → ₹12,000; Total: ₹2,00,000 → ₹2,12,000.")

        # Reworded but no longer or dearer: the entry says it was edited.
        q = self.get(f"/api/quotations/{q['id']}/")
        renamed = [{**l, 'position': i} for i, l in enumerate(q['spec_lines'])]
        renamed[0]['brand'] = 'Adani'
        self.edit(q, spec_lines=renamed,
                  costs=[{'remark': 'Crane hire, 3rd floor', 'amount': '12000', 'position': 0}])
        latest = max(self.entries('quotation_edited'), key=lambda e: e['id'])
        self.assertEqual(latest['description'],
                         f"Quotation {q['number']} edited — Specifications edited; "
                         f"Additional costs edited.")

    def test_switching_the_variant_lists_the_price_it_brought_with_it(self):
        q = self.raise_quotation()
        r = self.edit(q, price_variant='non_dcr')
        self.assertEqual(r.status_code, 200, r.content[:300])
        [entry] = self.entries('quotation_edited')
        self.assertEqual(entry['description'],
                         f"Quotation {q['number']} edited — Variant: DCR → Non-DCR; "
                         f"Package price: ₹2,00,000 → ₹1,80,000; Total: ₹2,00,000 → ₹1,80,000.")

    def test_moving_it_to_another_customer_is_told_on_both_timelines(self):
        other = Lead.objects.create(first_name='Meera', last_name='Nair', phone='9990011002')
        q = self.raise_quotation()
        self.edit(q, lead=other.id)
        for lead in (self.lead, other):
            [entry] = self.entries('quotation_edited', lead)
            self.assertEqual(entry['description'],
                             f"Quotation {q['number']} edited — Customer: Ravi Kumar → Meera Nair.")

    def test_a_refused_edit_leaves_no_entry(self):
        q = self.raise_quotation()
        Quotation.objects.filter(pk=q['id']).update(order_converted_at=timezone.now())
        r = self.edit(q, discount_amount='15000', discount_remark='Too late')
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertEqual(self.entries('quotation_edited'), [])

    def test_a_quotation_is_never_saved_without_its_entry(self):
        """Recorded in the same transaction: if the entry cannot be written, the
        quotation is not saved either, and nothing is half-done."""
        with patch('inventory.quotation_timeline.record_created',
                   side_effect=RuntimeError('timeline down')):
            with self.assertRaises(RuntimeError), self.assertLogs('django.request', 'ERROR'):
                self.send('post', '/api/quotations/',
                          {'lead': self.lead.id, 'project': self.project['id'],
                           'quotation_date': '2026-09-01'})
        self.assertFalse(Quotation.objects.exists())
