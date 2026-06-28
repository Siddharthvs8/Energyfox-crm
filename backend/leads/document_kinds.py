"""Shared customer documents — one copy per customer, inherited across stages.

A customer document (Aadhaar, PAN, Passbook, …) is entered **once** and is then
inherited by every slot of the same canonical *kind* in every stage — the BDE's
site visit and Documentation Stage 1. There is a single underlying file, so
viewing / changing / deleting it from any stage affects everyone (e.g. a wrong
Aadhaar uploaded by the BDE can be corrected by documentation staff later).

Slots **not** listed here stay stage-local (site-visit photos, the generated
purchase-order/agreement PDFs, the loan passbook *copy*) — they keep their own
per-stage storage.

This module is plain constants/helpers (no Django models) so it is safe to import
from migrations as well as views/serializers.
"""

# Canonical kind -> display label.
SHARED_KIND_LABELS = {
    'aadhaar': 'Aadhaar',
    'pan': 'PAN',
    'passbook': 'Passbook',
    'kseb_bill': 'KSEB Bill',
    'land_tax': 'Land Tax',
    'ownership_certificate': 'Ownership Certificate',
    'building_certificate': 'Building Certificate',
    'customer_photo': 'Customer Photo',
    'itr': 'ITR',
    'loan_document': 'Loan Document',
}

# Every stage slot doc_type -> its canonical kind. Slots absent here are
# stage-local and never shared.
SLOT_TO_KIND = {
    # ── BDE site visit (SiteVisitDocument doc_types) ──
    'aadhaar_card': 'aadhaar',
    'pan_card': 'pan',
    'passbook': 'passbook',
    'kseb_bill_file': 'kseb_bill',
    'land_tax': 'land_tax',
    'ownership_certificate': 'ownership_certificate',
    'building_certificate': 'building_certificate',
    'customer_passport_photo': 'customer_photo',
    'itr_report': 'itr',
    'loan_document': 'loan_document',
    # ── Documentation Stage 1 (DocumentationStage1Document doc_types) ──
    'nc_aadhaar': 'aadhaar',
    'nc_kseb_bill': 'kseb_bill',
    'nc_landtax': 'land_tax',
    'nc_ownership': 'ownership_certificate',
    'nc_building_certificate': 'building_certificate',
    'nc_customer_photo': 'customer_photo',
    'le_aadhaar': 'aadhaar',
    'mnre_aadhaar': 'aadhaar',
    'mnre_pan': 'pan',
    'mnre_passbook': 'passbook',
    'mnre_kseb_bill': 'kseb_bill',
    'loan_aadhaar': 'aadhaar',
    'loan_pan': 'pan',
    'loan_passbook': 'passbook',
    'loan_land_tax': 'land_tax',
    'loan_itr': 'itr',
    # Stage-local (deliberately NOT shared): mnre_purchase_order,
    # loan_agreement_purchase_order, loan_passbook_copy, all photo_*.
}

# Shared slots per stage, in the order they should appear. Used to project the
# lead's shared documents onto each stage's slots (the same Aadhaar appears under
# every Aadhaar slot of that stage, e.g. mnre_aadhaar AND loan_aadhaar).
SITE_VISIT_SHARED_SLOTS = [
    'aadhaar_card', 'pan_card', 'passbook', 'kseb_bill_file', 'land_tax',
    'ownership_certificate', 'building_certificate', 'customer_passport_photo',
    'itr_report', 'loan_document',
]
DOC_STAGE1_SHARED_SLOTS = [
    'nc_aadhaar', 'nc_kseb_bill', 'nc_landtax', 'nc_ownership',
    'nc_building_certificate', 'nc_customer_photo', 'le_aadhaar',
    'mnre_aadhaar', 'mnre_pan', 'mnre_passbook', 'mnre_kseb_bill',
    'loan_aadhaar', 'loan_pan', 'loan_passbook', 'loan_land_tax', 'loan_itr',
]


def kind_for(doc_type):
    """Canonical shared kind for a slot doc_type, or None if it's stage-local."""
    return SLOT_TO_KIND.get(doc_type)


def shared_doc_entries(lead, slots):
    """Project a lead's shared documents onto the given stage slots.

    Returns a flat list of dicts shaped like the per-stage document serializers
    (``id, doc_type, file, uploaded_at``) plus ``shared``/``kind`` so the client
    can route delete to the shared-document endpoint. The same underlying file is
    emitted once per slot of its kind, so it shows up in every matching slot.
    """
    from collections import defaultdict
    by_kind = defaultdict(list)
    for d in lead.shared_documents.all():
        by_kind[d.kind].append(d)
    out = []
    for slot in slots:
        kind = SLOT_TO_KIND.get(slot)
        for d in by_kind.get(kind, []):
            out.append({
                'id': d.id,
                'doc_type': slot,
                'file': d.file.url if d.file else None,
                'uploaded_at': d.uploaded_at,
                'shared': True,
                'kind': kind,
            })
    return out
