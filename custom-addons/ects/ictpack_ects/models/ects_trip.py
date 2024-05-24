# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

TRIP_STATE_SELECTION = [
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('issued', 'Issued'),
        ('in-transit', 'In Transit'),
        ('unlocked', 'Trip End'),
        ('rejected', 'Rejected'),
        ('waiting', 'Waiting Cancellation'),
        ('cancelled', 'Cancelled')
]

class EctsTrips(models.Model):
    _name = 'ects.trip'
    _description = 'Ects Trips'
    _rec_name = 'number'
    _order = 'create_date desc'
    _inherit = 'mail.thread'

    # Other Info
    number = fields.Char('Trip Number')
    customer_name = fields.Many2one('res.partner')
    employee_id = fields.Many2one('hr.employee',tracking=True)
    source_location = fields.Many2one('hr.work.location', string='Source Location')
    destination = fields.Many2one('hr.work.location', string='Border')
    driver_id = fields.Many2one('res.partner')
    agent_name = fields.Many2one('res.partner', string='Agent Name')
    # e_seal_id = fields.Many2one('product.template', 'Electronic Seal ID', domain=[('is_master_lock', '=', True)])
    lock_assigned_employee_id = fields.Integer(related="employee_id.id")
    e_seal_id = fields.Many2one('stock.lot', 'Electronic Seal ID',
                                domain="[('ects_assigned_to', '=', lock_assigned_employee_id)]", tracking=True)
    cargo_type = fields.Many2one('ects.cargo.type', string='Cargo Type',tracking=True)
    cargo_number = fields.Char('Cargo Number',tracking=True)  # chassis number or container number
    car_type = fields.Char('Car Type')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    # Payments
    payment_type = fields.Many2one('ects.payment.type',tracking=True)
    amount_received = fields.Float('Amount Received',tracking=True)

    # Gate Info
    gate_number = fields.Many2one('hr.work.location')
    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    passport_number = fields.Char('Passport Number')

    state = fields.Selection(TRIP_STATE_SELECTION, default='draft', tracking=True)
    submitted_at = fields.Datetime('Submitted Time',tracking=True)
    issued_at = fields.Datetime('Issued Time',tracking=True)
    approved_at = fields.Datetime('Approved Time')
    rejected_at = fields.Datetime('Rejected Time')
    cancelled_at = fields.Datetime('Cancelled Time')
    active = fields.Boolean(default=True,tracking=True)
    slave_count = fields.Integer('Slave Count')
    is_swapped = fields.Boolean('Swapped',tracking=True)
    is_reconcilled = fields.Boolean('Reconcilled',tracking=True)
    cancellation_reasons = fields.Char('Cancellation Reasons')
    container_horse = fields.Char('Container Horse', default="")
    container_trailer = fields.Char('Container Trailer', default="")
    car_plate_number = fields.Char('Car Plate Number', default="")

    def trip_reconcilled(self):
        for record in self:
            record.is_reconcilled = True

    def trip_unreconcilled(self):
        for record in self:
            record.is_reconcilled = False

    @api.model_create_multi
    def create(self, values):
        res = super(EctsTrips, self).create(values)
        if res:
            for rec in res:
                if rec.e_seal_id:
                    if rec.payment_type.key == 'credit':
                        rec.amount_received = rec.cargo_type.credit_master_price + (rec.cargo_type.credit_slave_price * rec.slave_count)
                    else:
                        rec.amount_received = rec.cargo_type.master_price + (rec.cargo_type.slave_price * rec.slave_count)
                if rec.payment_type.requires_approval:
                    rec.state = 'pending'
                    rec.submitted_at = fields.datetime.now()
        return res

    def write(self, vals):
        res = super(EctsTrips, self).write(vals)
        if res:
            for rec in self:
                if rec.is_swapped and rec.state == 'issued':
                    rec.e_seal_id.ects_state = 'sold'
        return res

    def submit_trip(self):
        for rec in self:
            rec.state = 'pending'
            rec.submitted_at = fields.datetime.now()

    def approve_trip(self):
        for rec in self:
            rec.state = 'approved'
            rec.approved_at = fields.datetime.now()

    def reject_trip(self):
        for rec in self:
            rec.state = 'rejected'
            rec.rejected_at = fields.datetime.now()

    def cancel_trip_button(self):
        for rec in self:
            rec.state = 'waiting'

    def confirm_cancel_trip_button(self):
        for rec in self:
            rec.state = 'cancelled'
            rec.cancelled_at = fields.datetime.now()

    def issue_receipt(self):
        for rec in self:
            rec.state = 'issued'
            rec.issued_at = fields.datetime.now()
            rec.e_seal_id.ects_state = 'sold'

    def activate_device(self, e_seal_id=None):
        if e_seal_id is None:
            e_seal_id = self.e_seal_id.id
        device_obj = self.env['stock.quant'].search([('lot_id', '=', e_seal_id), ('quantity', '>=', 1)])
        for rec in device_obj:
            picking_type_id = self.env['stock.picking.type'].search([('type_code', '=', 'transit')], limit=1).id
            transfer = self.env['stock.picking'].create(
                {'picking_type_id': picking_type_id, 'location_id': rec.location_id.id})
            if transfer:
                # Create a stock move
                move_vals = {
                    'product_id': rec.product_id.id,
                    'product_uom_qty': 1,
                    'picking_id': transfer.id,
                    'location_id': rec.location_id.id,
                    'location_dest_id': transfer.location_dest_id.id,
                    'name': rec.product_id.name
                }
                move = self.env['stock.move'].create(move_vals)

                # Create a stock move line
                lot_id = self.env['stock.lot'].search([('name', '=', e_seal_id)], limit=1).id
                line_vals = {
                    'move_id': move.id,
                    'picking_id': transfer.id,
                    'company_id': self.company_id.id,
                    'product_id': rec.product_id.id,
                    'location_id': rec.location_id.id,
                    'location_dest_id': transfer.location_dest_id.id,
                    'lot_id': lot_id,
                    'qty_done': 1
                }
                line = self.env['stock.move.line'].create(line_vals)

                # Update transfer with moves and move lines.
                transfer.move_line_ids_without_package = [line.id]

                # Confirm, Assign and Validate.
                if transfer.action_confirm() and transfer.action_assign() and transfer.button_validate():
                    # Change Lot Ects state
                    self.e_seal_id.ects_state = 'in-transit'

    def reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'
            

    def return_ects_trips(self, employee_id):
        trips = self.search([('employee_id', '=', int(employee_id))])
        values = []
        for rec in trips:
            vals = {
                "id": rec.id,
                "name": rec.number,
                "employee_id": rec.employee_id.name,
                "customer_name": rec.customer_name.name,
                "source_location": rec.source_location.name,
                "destination": rec.destination.name,
                "driver_id": rec.driver_id.name,
                "driver_phone": rec.driver_id.phone,
                "agent_name": rec.agent_name.name,
                "passport_number": rec.passport_number,
                "e_seal_id": rec.e_seal_id.name,
                "cargo_type": rec.cargo_type.name,
                "cargo_number": rec.cargo_number,
                "car_type": rec.car_type,
                "payment_type": rec.payment_type.name,
                "amount_received": rec.amount_received,
                "gate_number": rec.gate_number.name,
                "state_desc": dict(TRIP_STATE_SELECTION)[rec.state],
                "state": rec.state,
                "created_date": rec.create_date,
                "created_by": rec.employee_id.id,
                "start_date": rec.start_date,
                "end_date": rec.end_date,
                "container_horse": rec.container_horse,
                "container_trailer": rec.container_trailer,
                "car_plate_number": rec.car_plate_number
            }
            values.append(vals)
        return values

    def return_ects_trips_by_id(self, trip_id):
        trips = self.search([('id', '=', int(trip_id))])
        values = []
        for rec in trips:
            vals = {
                "id": rec.id,
                "name": rec.number,
                "employee_id": rec.employee_id.name,
                "customer_name": rec.customer_name.name,
                "source_location": rec.source_location.name,
                "destination": rec.destination.name,
                "driver_id": rec.driver_id.name,
                "driver_phone": rec.driver_id.phone,
                "agent_name": rec.agent_name.name,
                "passport_number": rec.passport_number,
                "e_seal_id": rec.e_seal_id.name,
                "cargo_type": rec.cargo_type.name,
                "cargo_number": rec.cargo_number,
                "car_type": rec.car_type,
                "payment_type": rec.payment_type.name,
                "amount_received": rec.amount_received,
                "gate_number": rec.gate_number.name,
                "state_desc": dict(TRIP_STATE_SELECTION)[rec.state],
                "state": rec.state,
                "created_date": rec.create_date,
                "created_by": rec.employee_id.id,
                "start_date": rec.start_date,
                "end_date": rec.end_date,
                "container_horse": rec.container_horse,
                "container_trailer": rec.container_trailer,
                "car_plate_number": rec.car_plate_number
            }
            values.append(vals)
        return values

    def swap(self, trip_id):
        trip = self.browse(trip_id)
        device = self.env['stock.lot'].search([('id', '=', trip.e_seal_id.id)])
        trip.is_swapped = True
        device.ects_state = 'for-sale'
        return {"trip_id": trip_id}

    def cancel_trip(self, trip_id, cancel_reason):
        trip = self.browse(trip_id)
        if trip:
            trip.cancel_trip_button()
            trip.cancellation_reasons = cancel_reason
            trip.e_seal_id.ects_state = 'for-sale'
            return {"success": True}
        else:
            return {"success": False}

    @api.depends('receipt_number')
    def _compute_receipt_number(self):
        pass


class PaymentType(models.Model):
    _name = 'ects.payment.type'
    _description = 'Payment Type'
    _rec_name = 'name'

    name = fields.Char(required=True)
    key = fields.Char(required=True)
    requires_approval = fields.Boolean(default=False)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
