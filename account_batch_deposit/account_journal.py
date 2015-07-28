# -*- coding: utf-8 -*-

from openerp import models, fields, api, _

class AccountJournal(models.Model):
    _inherit = "account.journal"

    batch_deposit_sequence_id = fields.Many2one('ir.sequence', 'Batch Deposit Sequence', readonly=True, copy=False,
        help="Automatically generates references for batch deposits.")
    batch_deposit_payment_method_selected = fields.Boolean(compute='_compute_batch_deposit_payment_method_selected',
        help="Technical feature used to know whether batch deposit was enabled as payment method.")

    @api.one
    @api.depends('inbound_payment_method_ids')
    def _compute_batch_deposit_payment_method_selected(self):
        self.batch_deposit_payment_method_selected = any(pm.code == 'batch_deposit' for pm in self.inbound_payment_method_ids)

    def _default_inbound_payment_methods(self):
        vals = super(AccountJournal, self)._default_inbound_payment_methods()
        return vals + self.env.ref('account_batch_deposit.account_payment_method_batch_deposit')

    @api.model
    def create(self, vals):
        if not vals.get('batch_deposit_sequence_id'):
            vals.update({'batch_deposit_sequence_id': self._create_batch_deposit_sequence(vals).id})
        return super(AccountJournal, self.sudo()).create(vals)

    @api.one
    def copy(self, default=None):
        rec = super(AccountJournal, self).copy(default)
        rec.write({'batch_deposit_sequence_id': self._create_batch_deposit_sequence({'name': rec.name, 'company_id': rec.company_id.id}).id})
        return rec

    @api.model
    def _create_batch_deposit_sequence(self, vals):
        return self.env['ir.sequence'].sudo().create({
            'name': vals['name'] + ": " + _("Batch Deposits Sequence"),
            'padding': 4,
            'number_next': 1,
            'number_increment': 1,
            'use_date_range': True,
            'prefix': 'DEPOSIT/%(year)s/',
            'company_id': vals.get('company_id', self.env.user.company_id.id),
        })

    @api.model
    def _enable_batch_deposit_on_bank_journals(self):
        """ Enables batch deposit payment method on bank journals. Called upon module installation via data file."""
        batch_deposit = self.env.ref('account_batch_deposit.account_payment_method_batch_deposit')
        for bank_journal in self.search([('type', '=', 'bank')]):
            batch_deposit_sequence = self._create_batch_deposit_sequence({'name': bank_journal.name, 'company_id': bank_journal.company_id.id})
            bank_journal.write({
                'inbound_payment_method_ids': [(4, batch_deposit.id, None)],
                'batch_deposit_sequence_id': batch_deposit_sequence.id,
            })