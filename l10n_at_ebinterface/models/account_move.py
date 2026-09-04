from odoo import api, models

from lxml import etree

EBI_NS = "http://www.ebinterface.at/schema/6p1/"

# Maps a tax rate to the closest EN 16931 / ebInterface VAT category code.
# Reverse charge / exempt / export cases are not auto-detected here and
# always fall back to "E" (Exempt) - review those manually.
TAX_CATEGORY_BY_RATE = {
    20.0: "S",   # Standard rate
    13.0: "AB",  # Reduced rate (second)
    10.0: "AA",  # Reduced rate (first)
}


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def _l10n_at_ebinterface_tax_category(self, rate):
        if rate in TAX_CATEGORY_BY_RATE:
            return TAX_CATEGORY_BY_RATE[rate]
        if rate == 0:
            return "E"
        return "S"

    def _l10n_at_ebinterface_bank_account(self):
        self.ensure_one()
        bank = self.company_id.partner_id.bank_ids.filtered(lambda b: b.bank_id and b.bank_id.bic)[:1]
        return bank

    def _l10n_at_ebinterface_generate_xml(self):
        """Generate an ebInterface 6.1 XML e-invoice for this customer invoice.

        Reference: https://www.erechnung.gv.at/erb/de_AT/tec_formats_ebinterface
        Schema: https://github.com/austriapro/ebinterface-standards (6p1/Invoice.xsd)
        """
        self.ensure_one()
        assert self.move_type in ("out_invoice", "out_refund"), \
            "ebInterface generation is only supported for customer invoices/credit notes"

        nsmap = {None: EBI_NS}
        root = etree.Element("Invoice", nsmap=nsmap)
        root.set("GeneratingSystem", "Odoo 19")
        root.set("DocumentType", "CreditMemo" if self.move_type == "out_refund" else "Invoice")
        root.set("InvoiceCurrency", self.currency_id.name)
        root.set("DocumentTitle", self.name or "")
        root.set("Language", (self.partner_id.lang or "de_DE")[:2])

        etree.SubElement(root, "InvoiceNumber").text = self.name or ""
        etree.SubElement(root, "InvoiceDate").text = str(self.invoice_date or self.date)

        biller = etree.SubElement(root, "Biller")
        etree.SubElement(biller, "VATIdentificationNumber").text = self.company_id.vat or "ATU00000000"
        biller_address = etree.SubElement(biller, "Address")
        etree.SubElement(biller_address, "Name").text = self.company_id.name
        if self.company_id.street:
            etree.SubElement(biller_address, "Street").text = self.company_id.street
        etree.SubElement(biller_address, "Town").text = self.company_id.city or "-"
        etree.SubElement(biller_address, "ZIP").text = self.company_id.zip or "-"
        biller_country = etree.SubElement(biller_address, "Country")
        biller_country.set("CountryCode", self.company_id.country_id.code or "AT")
        biller_country.text = self.company_id.country_id.name or "Österreich"

        recipient = etree.SubElement(root, "InvoiceRecipient")
        partner = self.partner_id.commercial_partner_id
        etree.SubElement(recipient, "VATIdentificationNumber").text = partner.vat or "ATU00000000"
        recipient_address = etree.SubElement(recipient, "Address")
        etree.SubElement(recipient_address, "Name").text = partner.name or "-"
        if partner.street:
            etree.SubElement(recipient_address, "Street").text = partner.street
        etree.SubElement(recipient_address, "Town").text = partner.city or "-"
        etree.SubElement(recipient_address, "ZIP").text = partner.zip or "-"
        recipient_country = etree.SubElement(recipient_address, "Country")
        recipient_country.set("CountryCode", partner.country_id.code or "AT")
        recipient_country.text = partner.country_id.name or "Österreich"

        details = etree.SubElement(root, "Details")
        item_list = etree.SubElement(details, "ItemList")
        position = 0
        for line in self.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
            position += 1
            li = etree.SubElement(item_list, "ListLineItem")
            etree.SubElement(li, "PositionNumber").text = str(position)
            etree.SubElement(li, "Description").text = (line.name or "").strip() or "-"
            qty = etree.SubElement(li, "Quantity")
            qty.set("Unit", line.product_uom_id.name if line.product_uom_id else "pce")
            qty.text = f"{line.quantity:.4f}"
            etree.SubElement(li, "UnitPrice").text = f"{line.price_unit:.4f}"

            rate = line.tax_ids[:1].amount if line.tax_ids else 0.0
            tax_item = etree.SubElement(li, "TaxItem")
            etree.SubElement(tax_item, "TaxableAmount").text = f"{line.price_subtotal:.2f}"
            tax_percent = etree.SubElement(tax_item, "TaxPercent")
            tax_percent.set("TaxCategoryCode", self._l10n_at_ebinterface_tax_category(rate))
            tax_percent.text = f"{rate:.2f}"

            etree.SubElement(li, "LineItemAmount").text = f"{line.price_subtotal:.2f}"

        tax_node = etree.SubElement(root, "Tax")
        for subtotal in self.tax_totals.get("subtotals", []):
            for group in subtotal.get("tax_groups", []):
                taxes = self.env["account.tax"].browse(group["involved_tax_ids"])
                rate = taxes[:1].amount if taxes else 0.0
                tax_item = etree.SubElement(tax_node, "TaxItem")
                etree.SubElement(tax_item, "TaxableAmount").text = f"{group['base_amount_currency']:.2f}"
                tax_percent = etree.SubElement(tax_item, "TaxPercent")
                tax_percent.set("TaxCategoryCode", self._l10n_at_ebinterface_tax_category(rate))
                tax_percent.text = f"{rate:.2f}"
                etree.SubElement(tax_item, "TaxAmount").text = f"{group['tax_amount_currency']:.2f}"

        etree.SubElement(root, "TotalGrossAmount").text = f"{self.amount_total:.2f}"
        etree.SubElement(root, "PayableAmount").text = f"{self.amount_total:.2f}"

        bank = self._l10n_at_ebinterface_bank_account()
        if bank:
            payment_method = etree.SubElement(root, "PaymentMethod")
            ubt = etree.SubElement(payment_method, "UniversalBankTransaction")
            beneficiary = etree.SubElement(ubt, "BeneficiaryAccount")
            if bank.bank_id and bank.bank_id.name:
                etree.SubElement(beneficiary, "BankName").text = bank.bank_id.name
            if bank.bank_id and bank.bank_id.bic:
                etree.SubElement(beneficiary, "BIC").text = bank.bank_id.bic
            etree.SubElement(beneficiary, "IBAN").text = (bank.sanitized_acc_number or bank.acc_number or "").replace(" ", "")
            etree.SubElement(beneficiary, "BankAccountOwner").text = self.company_id.name
            etree.SubElement(ubt, "PaymentReference").text = self.payment_reference or self.name or ""

        if self.invoice_date_due:
            payment_conditions = etree.SubElement(root, "PaymentConditions")
            etree.SubElement(payment_conditions, "DueDate").text = str(self.invoice_date_due)

        return etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", pretty_print=True
        )

    def _l10n_at_ebinterface_attachment_name(self):
        self.ensure_one()
        return f"ebinterface-{(self.name or 'invoice').replace('/', '_')}.xml"

    def _l10n_at_ebinterface_get_or_create_attachment(self):
        """Return the ebInterface XML ir.attachment for this invoice, generating
        it if it doesn't exist yet (or regenerating if the invoice changed
        since it was last generated)."""
        self.ensure_one()
        name = self._l10n_at_ebinterface_attachment_name()
        attachment = self.env["ir.attachment"].search([
            ("res_model", "=", "account.move"),
            ("res_id", "=", self.id),
            ("name", "=", name),
        ], limit=1)
        xml_content = self._l10n_at_ebinterface_generate_xml()
        if attachment:
            if attachment.raw != xml_content:
                attachment.write({"raw": xml_content})
            return attachment
        return self.env["ir.attachment"].create({
            "name": name,
            "raw": xml_content,
            "res_model": "account.move",
            "res_id": self.id,
            "mimetype": "application/xml",
        })
