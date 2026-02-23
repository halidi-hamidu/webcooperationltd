# -*- coding: utf-8 -*-
##############################################################################
#
# Cronquotech
# Copyright (C) 2022 (https://cronquotech.odoo.com)
#
##############################################################################

from odoo import models, fields, api
from odoo.exceptions import UserError

class AccountMove(models.Model):

    _inherit = 'account.move'

    is_seq_generated = fields.Boolean(string="Sequence Generated", copy=False)

    @api.depends('posted_before', 'state', 'journal_id', 'date')
    def _compute_name(self):
        """Computes the field is_seq_generated based on conditions."""
        for move in self:
            if not move.journal_id.seq_id:
              return super(AccountMove, self)._compute_name()
            seq_id = move._get_sequence()
            if not seq_id:
                raise UserError('Please define a sequence on your journal.')
            if not move.is_seq_generated and move.state == 'draft':
                move.name = '/'
            elif not move.is_seq_generated and move.state != 'draft':
                move.name = seq_id.next_by_id()
                move.is_seq_generated = True

    def _get_sequence(self):
        """Returns sequence number based on condition."""
        self.ensure_one()

        journal = self.journal_id
        if self.move_type in ('entry', 'out_invoice', 'in_invoice', 'out_receipt', 'in_receipt') or not journal.refund_sequence:
            return journal.seq_id
        if not journal.refund_seq_id:
            return
        return journal.refund_seq_id

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: