# Odoo 19 Invoice E-Files

Three modules for Odoo 19 Community:

1. **ebInterface 6.1** (Austria) - a custom XML generator, since no Odoo
   core module or OCA repo supports Austria's native e-invoice format for
   any current Odoo version.
2. **ZUGFeRD** (Germany, but usable by any company) - Odoo 19 core already
   generates this (a hybrid PDF/A-3 with an embedded CII XML); this repo
   just forces it onto every send instead of it being a per-customer
   opt-in, and fixes two gaps in core that stop it from actually working
   outside France/Germany.
3. **Automatic submission to e-Rechnung.gv.at** - the Austrian government's
   B2G e-invoicing webservice, for customers who require it (public sector
   recipients, mainly).

The first two attach automatically to every customer invoice/credit note
sent from Odoo; the third additionally submits the ebInterface XML
straight to the government webservice for the specific customers it's
enabled for.

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

### `l10n_at_erechnung_gv_at`

Depends on `l10n_at_ebinterface` and `account_invoice_zugferd_ebinterface_auto`.
Submits the ebInterface XML to the [e-Rechnung.gv.at webservice](https://www.erechnung.gv.at/erb/en_GB/tec_delivery_ws)
(`deliverInvoice` SOAP operation, WSDL 2.0 - `data/erb-in-invoice-201.wsdl`,
vendored locally rather than fetched at runtime) via [`zeep`](https://pypi.org/project/zeep/),
authenticated with WS-Security UsernameToken over the Unternehmensserviceportal (USP).

**Settings (Accounting settings > e-Rechnung.gv.at)**: USP webservice
username/password, and a Test/Produktiv environment dropdown -
`https://txm.portal.at/at.gv.bmf.erb.test/V2` vs. `https://txm.portal.at/at.gv.bmf.erb/V2`.

**Per customer (Contacts, Sales & Purchase tab, Austrian customers only)**:
a "Automatisch an e-Rechnung.gv.at senden" checkbox, which a
`@api.constrains` refuses to enable unless the customer's country is
Austria *and* all three of these (added by `l10n_at_ebinterface`) are
filled in:

| Field | ebInterface XML path |
|---|---|
| Lieferantennummer | `Biller/InvoiceRecipientsBillerID` |
| Einkäufergruppe (Filialnummer) | combined with Auftragsreferenz as `Biller`'s Order... |
| Auftragsreferenz | ...`InvoiceRecipient/OrderReference/OrderID` = `"<EKG>:<Auftragsreferenz>"` |

That `EKG:Referenz` composition (and the alternative pure-10-digit-order-number
or pure-3-character-EKG forms) is specified in BRZ's official
["Leitfaden Rechnungsstellung und -einbringung"](https://www.erechnung.gv.at/files/Leitfaden%20Rechnungsstellung%20und%20-einbringung%20V%202_7%2020240913.pdf),
§8.3.

**Sending**: hooks `account.move.send._hook_if_success` - when a customer
invoice with `l10n_at_erb_auto_send` enabled is sent (email, print, or
otherwise), it's also submitted automatically. A manual "An
e-Rechnung.gv.at senden" button and a status badge (Nicht gesendet /
Übermittelt / Fehler) are on the invoice form for enabled customers, for
resending or checking what happened.

The WSDL was fetched from the official source
(`https://www.erechnung.gv.at/files/ws/erb-in-invoice-201.wsdl`) and its
request/response structure verified via `zeep`'s dry-run message
construction (`Client.create_message`) - the generated SOAP envelope,
WS-Security header and base64-encoded invoice payload were confirmed to
match the documented structure exactly. Submission to the live BRZ test
endpoint has *not* been exercised end-to-end (no test USP credentials
were available) - test with real credentials before relying on this in
production.

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
pip install zeep
```
then install `account_invoice_zugferd_ebinterface_auto` for ZUGFeRD +
ebInterface on every send, and/or `l10n_at_erechnung_gv_at` for the
government webservice submission (both pull in `l10n_at_ebinterface` as
a dependency).
