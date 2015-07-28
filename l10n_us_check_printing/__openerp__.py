# -*- coding: utf-8 -*-
{
    'name': 'US Check Printing',
    'version': '1.0',
    'author': 'Odoo SA',
    'category': 'Localization/Checks Printing',
    'summary': 'Print US Checks',
    'description': """
US Check Printing
=================
This module allows to print your payments on pre-printed check paper.
You can configure the output (layout, stubs informations, etc.) in company settings, and manage the checks numbering (if you use pre-printed checks without numbers) in journal settings.

Supported formats
-----------------
- Check on top : Quicken / QuickBooks standard
- Check on middle: Peachtree standard
- Check on bottom: ADP standard
    """,
    'website': 'https://www.odoo.com/page/accounting',
    'depends' : ['account_check_writing', 'l10n_us'],
    'data': [
        'data/us_check_printing.xml',
        'report/print_check.xml',
        'report/print_check_top.xml',
        'report/print_check_middle.xml',
        'report/print_check_bottom.xml',
        'views/account_payment_view.xml',
        'views/res_company_view.xml',
        'wizard/print_pre_numbered_checks.xml'
    ],
    'installable': True,
    'auto_install': True,
}