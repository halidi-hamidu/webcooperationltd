from odoo import fields, models, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ects_state = fields.Selection([
        ('in-stock', 'In Stock'),
        ('dispatched', 'Dispatched'),
        ('for-sale', 'For Sale'),
        ('activated', 'Activated'),
        ('in-transit', 'In Transit'),
        ('unlocked', 'Unlocked'),
        ('to-return', 'To Return')
    ], default='in-stock', string='ECTS State')
    dispatched_to = fields.Many2one('hr.employee', 'Dispatched To', domain=([('is_ects_employee', '=', True)]))
    is_ects_transfer = fields.Boolean('ECTS Tranfer?')

    def ects_status(self):
        pass

    def button_validate(self):
        # Update Lots With current Transfer(stock picking) and current assigned id
        res = super(StockPicking, self).button_validate()
        if res:
            print(res)
            for rec in self:
                rec.ects_state = 'dispatched'
                for line in rec.move_line_ids_without_package:
                    lot = self.env['stock.lot'].search([('id', '=', line.lot_id.id)])
                    lot.ects_assigned_to = rec.dispatched_to
                    lot.ects_state = 'dispatched'
                    lot.current_move_id = rec.id
        return res
