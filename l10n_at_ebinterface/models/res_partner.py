from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Fields required by Austrian public-sector recipients on top of the
    # base ebInterface invoice, per the official BRZ guide
    # ("Leitfaden Rechnungsstellung und -einbringung"):
    #  - Lieferantennummer  -> Biller/InvoiceRecipientsBillerID
    #  - Auftragsreferenz + Einkäufergruppe (EKG) combined as
    #    "<EKG>:<Auftragsreferenz>" -> InvoiceRecipient/OrderReference/OrderID
    l10n_at_ebi_supplier_number = fields.Char(
        string="Lieferantennummer",
        help="Supplier number this customer assigned to us (Lieferantennummer). "
             "Embedded as Biller/InvoiceRecipientsBillerID in the ebInterface XML.",
    )
    l10n_at_ebi_purchasing_group = fields.Char(
        string="Einkäufergruppe (Filialnummer)",
        size=3,
        help="3-character purchasing group / branch code (EKG) this customer "
             "assigned. Combined with the order reference as \"EKG:Referenz\" "
             "in InvoiceRecipient/OrderReference/OrderID.",
    )
    l10n_at_ebi_order_reference = fields.Char(
        string="Auftragsreferenz",
        help="Order/internal reference this customer assigned (max 50 characters). "
             "Combined with the purchasing group as \"EKG:Referenz\" in "
             "InvoiceRecipient/OrderReference/OrderID.",
    )

    def _l10n_at_ebi_order_id(self):
        """Build the OrderReference/OrderID value per the BRZ guide's
        "EKG:interne Referenz" format."""
        self.ensure_one()
        ekg = (self.l10n_at_ebi_purchasing_group or "").strip()
        ref = (self.l10n_at_ebi_order_reference or "").strip()
        if ekg and ref:
            return f"{ekg}:{ref}"
        return ekg or ref or None
