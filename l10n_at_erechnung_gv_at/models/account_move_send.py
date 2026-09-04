import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class AccountMoveSend(models.AbstractModel):
    _inherit = "account.move.send"

    @api.model
    def _hook_if_success(self, moves_data, from_cron=False):
        # EXTENDS 'account'
        super()._hook_if_success(moves_data, from_cron=from_cron)
        for move in moves_data:
            if move._l10n_at_erb_can_auto_send():
                try:
                    move._l10n_at_erb_submit()
                except Exception:
                    _logger.exception(
                        "Automatic e-Rechnung.gv.at submission failed for %s", move.display_name
                    )
