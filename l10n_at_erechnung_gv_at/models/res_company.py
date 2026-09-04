from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_at_erb_usp_username = fields.Char(
        string="USP Webservice-Benutzername",
        help="Technical Unternehmensserviceportal (USP) webservice user, "
             "created in USP administration with 'e-Rechnung.gv.at Webservice' "
             "(and, for the test system, 'e-Rechnung.gv.at Webservice (T)') enabled.",
    )
    l10n_at_erb_usp_password = fields.Char(string="USP Webservice-Passwort")
    l10n_at_erb_environment = fields.Selection(
        [("test", "Testumgebung"), ("prod", "Produktivumgebung")],
        string="e-Rechnung.gv.at Umgebung",
        default="test",
        required=True,
    )
