import io
import logging

from odoo import api, fields, models
from odoo.tools.pdf import OdooPdfFileReader, OdooPdfFileWriter

_logger = logging.getLogger(__name__)

CUSTOMER_INVOICE_TYPES = ("out_invoice", "out_refund")


class AccountMoveSend(models.AbstractModel):
    _inherit = "account.move.send"

    @api.model
    def _ensure_partner_bank_id(self, move):
        """The ZUGFeRD/Factur-X (CII) exporter requires move.partner_bank_id
        to be set, but it's a stored/computed field that many existing
        invoices never got populated with (its compute only fires when its
        own dependencies change, which bulk-migrated invoices never
        triggered). Fill it in with the company's own bank account rather
        than let every send fail on invoices that predate this."""
        if move.partner_bank_id:
            return
        bank = move.company_id.partner_id.bank_ids.filtered(lambda b: b.allow_out_payment)[:1] \
            or move.company_id.partner_id.bank_ids[:1]
        if bank:
            move.partner_bank_id = bank

    @api.model
    def _get_default_invoice_edi_format(self, move, **kwargs) -> str:
        # EXTENDS 'account'
        # Always attach a ZUGFeRD hybrid PDF to every customer invoice sent,
        # regardless of the customer's own configured e-invoicing format.
        if move.move_type in CUSTOMER_INVOICE_TYPES:
            self._ensure_partner_bank_id(move)
            return "zugferd"
        return super()._get_default_invoice_edi_format(move, **kwargs)

    @api.model
    def _get_invoice_extra_attachments(self, move):
        # EXTENDS 'account'
        attachments = super()._get_invoice_extra_attachments(move)
        if move.move_type in CUSTOMER_INVOICE_TYPES and move.state == "posted":
            attachments |= move._l10n_at_ebinterface_get_or_create_attachment()
        return attachments

    def _hook_invoice_document_after_pdf_report_render(self, invoice, invoice_data):
        # EXTENDS 'account_edi_ubl_cii'
        super()._hook_invoice_document_after_pdf_report_render(invoice, invoice_data)

        # account_edi_ubl_cii only converts the PDF to PDF/A-3 when the
        # *company* is based in France or Germany, even though ZUGFeRD is a
        # format any company can select - without that conversion the PDF
        # has the CII XML embedded but isn't actually PDF/A-3 compliant, so
        # it isn't a valid ZUGFeRD file. Force the same conversion for
        # companies elsewhere (e.g. Austria) when we forced the zugferd
        # format ourselves.
        ubl_cii_format = invoice_data.get('ubl_cii_xml_options', {}).get('ubl_cii_format')
        if ubl_cii_format not in ('facturx', 'zugferd') or invoice.country_code in ('FR', 'DE'):
            return

        pdf_values = invoice.invoice_pdf_report_id or invoice_data.get('pdf_attachment_values') \
            or invoice_data.get('proforma_pdf_attachment_values')
        if not pdf_values:
            return
        raw = pdf_values.raw if hasattr(pdf_values, 'raw') else pdf_values.get('raw')
        if not raw:
            return

        reader_buffer = io.BytesIO(raw)
        reader = OdooPdfFileReader(reader_buffer, strict=False)

        writer = OdooPdfFileWriter()
        writer.cloneReaderDocumentRoot(reader)
        if writer.is_pdfa:
            reader_buffer.close()
            return
        try:
            writer.convert_to_pdfa()
        except Exception:
            _logger.exception("Error while converting invoice %s to PDF/A for ZUGFeRD", invoice.display_name)
            reader_buffer.close()
            return

        content = self.env['ir.qweb']._render(
            'account_edi_ubl_cii.account_invoice_pdfa_3_facturx_metadata',
            {'title': invoice.name, 'date': fields.Date.context_today(self)},
        )
        if "<pdfaid:conformance>B</pdfaid:conformance>" in content:
            content = content.replace("<pdfaid:conformance>B</pdfaid:conformance>", "<pdfaid:conformance>A</pdfaid:conformance>")
        writer.add_file_metadata(content.encode())

        writer_buffer = io.BytesIO()
        writer.write(writer_buffer)
        new_raw = writer_buffer.getvalue()
        if hasattr(pdf_values, 'raw'):
            pdf_values.raw = new_raw
        else:
            pdf_values['raw'] = new_raw
        reader_buffer.close()
        writer_buffer.close()
