# Odoo 19 Invoice E-Files

Two modules that automatically attach two additional electronic invoice
files to every customer invoice/credit note sent from Odoo 19:

1. **ebInterface 6.1** (Austria) - a custom XML generator, since no Odoo
   core module or OCA repo supports Austria's native e-invoice format for
   any current Odoo version.
2. **ZUGFeRD** (Germany, but usable by any company) - Odoo 19 core already
   generates this (a hybrid PDF/A-3 with an embedded CII XML); this repo
   just forces it onto every send instead of it being a per-customer
   opt-in, and fixes two gaps in core that stop it from actually working
   outside France/Germany.

## Modules

### `l10n_at_ebinterface`

Generates an [ebInterface 6.1](https://www.erechnung.gv.at/erb/de_AT/tec_formats_ebinterface)
XML e-invoice for a customer invoice/credit note.

- Schema/samples used as reference: [austriapro/ebinterface-standards](https://github.com/austriapro/ebinterface-standards),
  `schemas/ebInterface6p1/Invoice.xsd`. Federal agencies accept 4.3/5.0/6.0/6.1;
  6.1 is current (7.0 is only in preparation).
- `account.move._l10n_at_ebinterface_generate_xml()` builds the XML.
  `_l10n_at_ebinterface_get_or_create_attachment()` returns a cached
  `ir.attachment`, regenerating it if the invoice changed since last time.
- Maps: `Biller` = your company, `InvoiceRecipient` = the customer, one
  `ListLineItem` per invoice line, one `TaxItem` per invoice line and one
  per tax-rate subtotal, `PaymentMethod` = the company's first bank
  account that has a BIC configured.
- **Known limitations** (all validated against the XSD, but not full
  EN 16931/ebInterface semantic coverage):
  - Tax category codes are mapped from the numeric rate only
    (20%→S, 13%→AB, 10%→AA, 0%→E). Reverse charge, intra-EU and export
    cases are not auto-detected and will show as "E" (Exempt) - review
    those invoices manually.
  - A customer with no VAT number gets the placeholder `ATU00000000`
    rather than omitting the (required) field.
  - Only one bank account is included in `PaymentMethod` (the company's
    first bank account with a BIC set).

### `account_invoice_zugferd_ebinterface_auto`

Depends on `l10n_at_ebinterface` and Odoo core's `account_edi_ubl_cii`.

- Overrides `account.move.send._get_default_invoice_edi_format` to always
  return `zugferd` for customer invoices/credit notes, regardless of the
  customer's own `invoice_edi_format` setting.
- Overrides `account.move.send._get_invoice_extra_attachments` to always
  include the ebInterface XML attachment for customer invoices.
- Fixes two gaps in `account_edi_ubl_cii` that otherwise break ZUGFeRD
  for any company not based in France or Germany:
  - `account_edi_cii.py`'s CII exporter unconditionally reads
    `move_line.deferred_start_date` / `.deferred_end_date`, but no module
    in Odoo 19 Community actually defines those fields - sending any
    invoice as ZUGFeRD/Factur-X crashes with `AttributeError`. Added as
    plain, always-empty fields so the exporter's existing "if
    line.deferred_..." guards behave like any invoice with no deferred
    revenue period.
  - `account_edi_ubl_cii`'s PDF/A-3 conversion (required for a file to
    actually *be* ZUGFeRD, not just have an XML attached) is hardcoded to
    only run when the company is based in France or Germany. Re-runs the
    same conversion (same PDF/A-3 metadata template) regardless of
    company country whenever we forced the zugferd format ourselves.
  - The CII exporter also requires `move.partner_bank_id` to be set,
    which is a stored/computed field many pre-existing invoices never
    got populated with (its compute only fires on its own dependency
    changes, which bulk-migrated invoices never triggered). Filled in
    with the company's own bank account when empty.

## What ZUGFeRD/ebInterface generation will refuse to send, correctly

Both are strict, schema-validated formats. Odoo's own CII exporter will
raise a clear error - not send a broken file - when an invoice is missing
data the standard requires, most commonly:

- The customer's address has no country set.
- An invoice line has no tax at all (every line needs an explicit rate,
  even 0%).
- The invoice has no `partner_bank_id` and the company has no bank
  account at all (rare - see the fix above for the common case).

These are data-quality gaps worth fixing at the source rather than
working around in the generator.

## Installation

```
addons_path = .../invoice-efiles
```
then install `account_invoice_zugferd_ebinterface_auto` (it pulls in
`l10n_at_ebinterface` as a dependency).
