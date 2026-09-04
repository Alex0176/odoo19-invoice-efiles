{
    "name": "Austria - e-Rechnung.gv.at Auto Submission",
    "summary": "Automatically submit ebInterface e-invoices to the Austrian government webservice",
    "category": "Accounting/Localizations",
    "version": "19.0.1.0.0",
    "license": "AGPL-3",
    "author": "Alex0176",
    "website": "https://github.com/Alex0176/odoo19-invoice-efiles",
    "depends": ["l10n_at_ebinterface", "account_invoice_zugferd_ebinterface_auto"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
        "views/account_move_views.xml",
    ],
    "external_dependencies": {"python": ["zeep"]},
    "installable": True,
}
