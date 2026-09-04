from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # account_edi_ubl_cii's Factur-X/ZUGFeRD (CII) exporter unconditionally
    # reads move_line.deferred_start_date / .deferred_end_date
    # (account_edi_ubl_cii/models/account_edi_cii.py), but no module in
    # Odoo 19 Community actually defines these fields, so sending any
    # invoice as ZUGFeRD/Factur-X crashes with AttributeError. Add them as
    # plain, always-empty fields so the exporter's "if line.deferred_..."
    # guards behave the same as for any invoice with no deferred revenue
    # period, instead of crashing on attribute access.
    deferred_start_date = fields.Date()
    deferred_end_date = fields.Date()
