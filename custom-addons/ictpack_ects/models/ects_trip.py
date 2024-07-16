# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT


class EctsTrips(models.Model):
    _name = 'ects.trip'
    _description = 'Ects Trips'
    _rec_name = 'number'
    _order = 'create_date desc'

    # Other Info
    number = fields.Char('Trip Number')
    customer_name = fields.Many2one('res.partner')
    employee_id = fields.Many2one('hr.employee')
    source_location = fields.Many2one('hr.work.location', string='Source Location')
    destination = fields.Many2one('hr.work.location', string='Border')
    driver_id = fields.Many2one('res.partner')
    agent_name = fields.Many2one('res.partner', string='Agent Name')
    # e_seal_id = fields.Many2one('product.template', 'Electronic Seal ID', domain=[('is_master_lock', '=', True)])
    lock_assigned_employee_id = fields.Integer(related="employee_id.id")
    e_seal_id = fields.Many2one('stock.lot', 'Electronic Seal ID',
                                domain="[('ects_assigned_to', '=', lock_assigned_employee_id)]")
    cargo_type = fields.Many2one('ects.cargo.type', string='Cargo Type')
    cargo_number = fields.Char('Cargo Number')  # chassis number or container number
    car_type = fields.Char('Car Type')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    # Payments
    payment_type = fields.Many2one('ects.payment.type')
    amount_received = fields.Float('Amount Received')

    # Gate Info
    gate_number = fields.Many2one('hr.work.location')
    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    passport_number = fields.Char('Passport Number')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('issued', 'Issued'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled')
    ], default='draft')
    submitted_at = fields.Datetime('Submitted Time')
    issued_at = fields.Datetime('Issued Time')
    approved_at = fields.Datetime('Approved Time')
    rejected_at = fields.Datetime('Rejected Time')
    cancelled_at = fields.Datetime('Cancelled Time')
    active = fields.Boolean(default=True)
    slave_count = fields.Integer('Slave Count')

    @api.onchange('e_seal_id')
    def update_amount(self):
        if self.e_seal_id:
            self.amount_received = self.e_seal_id.product_id.lst_price

    @api.model_create_multi
    def create(self, values):
        res = super(EctsTrips, self).create(values)

        if res:
            for rec in res:
                print(rec.driver_id.name)
                if rec.e_seal_id:
                    # rec.amount_received = rec.e_seal_id.product_id.lst_price
                    rec.amount_received = rec.cargo_type.master_price + (rec.cargo_type.slave_price * rec.slave_count)
                if rec.payment_type.requires_approval:
                    rec.state = 'pending'
                    rec.submitted_at = fields.datetime.now()
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

    def cancel_trip(self):
        for rec in self:
            rec.state = 'cancelled'
            rec.cancelled_at = fields.datetime.now()

    def issue_receipt(self):
        for rec in self:
            rec.state = 'issued'
            rec.issued_at = fields.datetime.now()
            rec.e_seal_id.ects_state = 'sold'

    def reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'

    def return_ects_trips(self, employee_id):
        trips = self.search([('employee_id', '=', int(employee_id))])

        values = []
        for rec in trips:
            # vals = {
            #     "id": rec.id,
            #     "name": rec.number,
            #     "employee_id": rec.employee_id.id,
            #     "source_location": rec.source_location.id,
            #     "destination": rec.destination.id,
            #     "driver_id": rec.driver_id.id,
            #     "agent_name": rec.agent_name.id,
            #     "e_seal_id": rec.e_seal_id.id,
            #     "cargo_type": rec.cargo_type.id,
            #     "cargo_number": rec.cargo_number,
            #     "car_type": rec.car_type,
            #     "payment_type": rec.payment_type.id,
            #     "amount_received": rec.amount_received,
            #     "gate_number": rec.gate_number.id
            # }

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
                "state": rec.state,
                "created_date": rec.create_date,
                "created_by": rec.employee_id.id,
                "start_date": rec.start_date,
                "end_date": rec.end_date

            }
            values.append(vals)
        return values

    def return_ects_trips_by_id(self, trip_id):
        trips = self.search([('id', '=', int(trip_id))])

        values = []
        for rec in trips:
            # vals = {
            #     "id": rec.id,
            #     "name": rec.number,
            #     "employee_id": rec.employee_id.id,
            #     "source_location": rec.source_location.id,
            #     "destination": rec.destination.id,
            #     "driver_id": rec.driver_id.id,
            #     "agent_name": rec.agent_name.id,
            #     "e_seal_id": rec.e_seal_id.id,
            #     "cargo_type": rec.cargo_type.id,
            #     "cargo_number": rec.cargo_number,
            #     "car_type": rec.car_type,
            #     "payment_type": rec.payment_type.id,
            #     "amount_received": rec.amount_received,
            #     "gate_number": rec.gate_number.id
            # }

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
                "state": rec.state,
                "created_date": rec.create_date,
                "created_by": rec.employee_id.id,
                "start_date": rec.start_date,
                "end_date": rec.end_date

            }
            values.append(vals)
        return values

    @api.depends('receipt_number')
    def _compute_receipt_number(self):
        pass


class PaymentType(models.Model):
    _name = 'ects.payment.type'
    _description = 'Payment Type'
    _rec_name = 'name'

    name = fields.Char(required=1)
    key = fields.Char(required=1)
    requires_approval = fields.Boolean(default=False)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
