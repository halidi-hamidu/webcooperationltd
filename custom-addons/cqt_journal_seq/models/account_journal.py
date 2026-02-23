# -*- coding: utf-8 -*-
##############################################################################
#
# Cronquotech
# Copyright (C) 2022 (https://cronquotech.odoo.com)
#
##############################################################################

from odoo import models, fields, api


class AccountJournal(models.Model):

    _inherit = 'account.journal'

    seq_id = fields.Many2one('ir.sequence', string='Entry Sequence',
                                  help="This field contains the information related to the numbering of the journal entries.",
                                  copy=False)
    refund_seq_id = fields.Many2one('ir.sequence', string='Credit Note Entry Sequence',
                                         help="This field contains the information related to the numbering of the credit note entries.",
                                         copy=False)
    seq_num_next = fields.Integer(string='Next Number',
                                          help='The next sequence number will be used for the next invoice.',
                                          compute='_compute_next_seq_number',
                                          inverse='_inverse_next_seq_number')
    refund_seq_num_next = fields.Integer(string='Credit Notes Next Number',
                                                 help='The next sequence number will be used for the next credit note.',
                                                 compute='_compute_refund_next_seq_number',
                                                 inverse='_inverse_refund_next_seq_number')

    @api.depends('seq_id.use_date_range', 'seq_id.number_next_actual')
    def _compute_next_seq_number(self):
        """This method computes the next sequence number"""
        for journal in self:
            if journal.seq_id:
                sequence = journal.seq_id._get_current_sequence()
                journal.seq_num_next = sequence.number_next_actual
            else:
                journal.seq_num_next = 1

    def _inverse_next_seq_number(self):
        """This method computes the next sequence number inverse."""
        for journal in self:
            if journal.seq_id and journal.seq_num_next:
                sequence = journal.seq_id._get_current_sequence()
                sequence.sudo().number_next = journal.seq_num_next

    @api.depends('refund_seq_id.use_date_range', 'refund_seq_id.number_next_actual')
    def _compute_refund_next_seq_number(self):
        """This method computes the next sequence number for refund"""
        for journal in self:
            if journal.refund_seq_id and journal.refund_sequence:
                sequence = journal.refund_seq_id._get_current_sequence()
                journal.refund_seq_num_next = sequence.number_next_actual
            else:
                journal.refund_seq_num_next = 1

    def _inverse_refund_next_seq_number(self):
        """This method computes the next sequence number inverse for refund"""
        for journal in self:
            if journal.refund_seq_id and journal.refund_sequence and journal.refund_seq_num_next:
                sequence = journal.refund_seq_id._get_current_sequence()
                sequence.sudo().number_next = journal.refund_seq_num_next

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: