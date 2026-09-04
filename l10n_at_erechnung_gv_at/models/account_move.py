import logging
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from zeep import Client
    from zeep.transports import Transport
    from zeep.wsse.username import UsernameToken
except ImportError:
    _logger.debug("zeep not found, e-Rechnung.gv.at submission is unavailable.")
    Client = None

WSDL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "erb-in-invoice-201.wsdl")
BINDING = "{http://erb.eproc.brz.gv.at/ws/invoicedelivery/201306/}WSInvoiceDeliveryBinding"
ENDPOINTS = {
    "test": "https://txm.portal.at/at.gv.bmf.erb.test/V2",
    "prod": "https://txm.portal.at/at.gv.bmf.erb/V2",
}


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_at_erb_state = fields.Selection(
        [("not_sent", "Nicht gesendet"), ("sent", "Übermittelt"), ("error", "Fehler")],
        string="e-Rechnung.gv.at Status",
        default="not_sent",
        copy=False,
    )
    l10n_at_erb_document_id = fields.Char(string="e-Rechnung.gv.at Dokument-ID", copy=False, readonly=True)
    l10n_at_erb_message = fields.Text(string="e-Rechnung.gv.at Meldung", copy=False, readonly=True)
    l10n_at_erb_auto_send_partner = fields.Boolean(
        related="partner_id.commercial_partner_id.l10n_at_erb_auto_send",
        string="e-Rechnung.gv.at Auto-Versand aktiv",
    )

    def _l10n_at_erb_get_client(self):
        self.ensure_one()
        if not Client:
            raise UserError(_("The 'zeep' python library is required to submit invoices to e-Rechnung.gv.at."))
        company = self.company_id
        if not company.l10n_at_erb_usp_username or not company.l10n_at_erb_usp_password:
            raise UserError(_(
                "The USP webservice username/password are not configured "
                "(Settings > Accounting > e-Rechnung.gv.at)."
            ))
        wsse = UsernameToken(
            company.l10n_at_erb_usp_username,
            company.l10n_at_erb_usp_password,
            use_digest=False,
        )
        client = Client(WSDL_PATH, transport=Transport(), wsse=wsse)
        endpoint = ENDPOINTS[company.l10n_at_erb_environment or "test"]
        return client.create_service(BINDING, endpoint)

    def _l10n_at_erb_can_auto_send(self):
        self.ensure_one()
        return (
            self.move_type in ("out_invoice", "out_refund")
            and self.state == "posted"
            and self.partner_id.commercial_partner_id.l10n_at_erb_auto_send
            and self.l10n_at_erb_state != "sent"
        )

    def _l10n_at_erb_submit(self):
        """Submit this invoice's ebInterface XML to the e-Rechnung.gv.at
        webservice (deliverInvoice operation).
        Reference: https://www.erechnung.gv.at/erb/en_GB/tec_delivery_ws
        WSDL: https://www.erechnung.gv.at/files/ws/erb-in-invoice-201.wsdl
        """
        self.ensure_one()
        xml_content = self._l10n_at_ebinterface_generate_xml()
        service = self._l10n_at_erb_get_client()

        try:
            response = service.deliverInvoice(
                Invoice={"_value_1": xml_content, "encoding": "UTF-8"},
                Settings={"language": "de"},
            )
        except Exception as exc:  # noqa: BLE001 - webservice/SOAP fault, report it on the move
            _logger.exception("e-Rechnung.gv.at submission failed for %s", self.display_name)
            self.write({
                "l10n_at_erb_state": "error",
                "l10n_at_erb_message": str(exc),
            })
            return False

        if response.Error is not None:
            details = "\n".join(
                f"- {d.Field + ': ' if d.Field else ''}{d.Message}"
                for d in (response.Error.ErrorDetail or [])
            ) or _("Unknown error.")
            self.write({
                "l10n_at_erb_state": "error",
                "l10n_at_erb_message": details,
            })
            return False

        success = response.Success
        self.write({
            "l10n_at_erb_state": "sent",
            "l10n_at_erb_document_id": success.DocumentID,
            "l10n_at_erb_message": _(
                "Erfolgreich übermittelt am %(date)s (Dokument-ID: %(doc_id)s).",
                date=fields.Datetime.now(), doc_id=success.DocumentID,
            ),
        })
        return True

    def action_l10n_at_erb_submit(self):
        for move in self:
            if not move.partner_id.commercial_partner_id.l10n_at_erb_auto_send:
                raise UserError(_(
                    "%s is not enabled for automatic e-Rechnung.gv.at submission.",
                    move.partner_id.commercial_partner_id.display_name,
                ))
            move._l10n_at_erb_submit()
