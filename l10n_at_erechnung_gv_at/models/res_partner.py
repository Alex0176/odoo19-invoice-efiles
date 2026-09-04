from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    l10n_at_erb_auto_send = fields.Boolean(
        string="Automatisch an e-Rechnung.gv.at senden",
        help="Every posted customer invoice/credit note for this customer is "
             "automatically submitted to the Austrian government e-Rechnung.gv.at "
             "webservice when sent, instead of relying on the customer to submit "
             "it themselves. Requires the customer's country to be Austria and "
             "the Lieferantennummer, Auftragsreferenz and Einkäufergruppe fields "
             "to be filled in.",
    )

    @api.constrains(
        "l10n_at_erb_auto_send",
        "country_id",
        "l10n_at_ebi_supplier_number",
        "l10n_at_ebi_order_reference",
        "l10n_at_ebi_purchasing_group",
    )
    def _check_l10n_at_erb_auto_send(self):
        for partner in self:
            if not partner.l10n_at_erb_auto_send:
                continue
            if partner.country_id.code != "AT":
                raise ValidationError(_(
                    "\"Automatisch an e-Rechnung.gv.at senden\" can only be enabled "
                    "for customers whose country is Austria (%s is set to %s).",
                    partner.display_name, partner.country_id.name or _("no country"),
                ))
            missing = [
                label for field, label in (
                    ("l10n_at_ebi_supplier_number", _("Lieferantennummer")),
                    ("l10n_at_ebi_order_reference", _("Auftragsreferenz")),
                    ("l10n_at_ebi_purchasing_group", _("Einkäufergruppe (Filialnummer)")),
                )
                if not (partner[field] or "").strip()
            ]
            if missing:
                raise ValidationError(_(
                    "\"Automatisch an e-Rechnung.gv.at senden\" requires the following "
                    "field(s) to be filled in for %(partner)s first: %(missing)s.",
                    partner=partner.display_name, missing=", ".join(missing),
                ))
