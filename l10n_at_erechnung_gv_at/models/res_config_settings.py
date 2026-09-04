from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_at_erb_usp_username = fields.Char(
        related="company_id.l10n_at_erb_usp_username", readonly=False,
    )
    l10n_at_erb_usp_password = fields.Char(
        related="company_id.l10n_at_erb_usp_password", readonly=False,
    )
    l10n_at_erb_environment = fields.Selection(
        related="company_id.l10n_at_erb_environment", readonly=False,
    )
