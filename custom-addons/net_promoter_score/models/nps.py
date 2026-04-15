from odoo import api, fields, models
from collections import defaultdict
import calendar
class NetPromoterScore(models.Model):
    _name = "net.promoter.score"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Net Promoter Score (NPS) Response"

    name = fields.Char(string="Name")
    email = fields.Char(string="Email")
    
    score = fields.Integer(
        string="Score",
        required=True,
        help="Net Promoter Score (NPS) value from 0 to 10",
        default=0,
        tracking=True,
    )

    is_submitted = fields.Boolean(string="Submitted", default=False, tracking=True)
    feedback = fields.Text(string="Feedback", tracking=True)

    voter_identification = fields.Char(
        string="Voter Type",
        compute="_compute_voter_identification",
        store=True,
        help="Classifies voter as Promoter, Passive, or Detractor",
    )

    
    def action_submit(self):
        for record in self:
            record.write({'is_submitted': True})

    @api.depends('score')
    def _compute_voter_identification(self):
        for record in self:
            if record.score < 7:
                record.voter_identification = 'Detractor'
            elif 7 <= record.score <= 8:
                record.voter_identification = 'Passive'
            else:
                record.voter_identification = 'Promoter'

    @api.model
    def get_monthly_nps_data(self):
        records = self.search([])

        # Initialize monthly data
        data = defaultdict(lambda: {"Promoter": 2000, "Passive": 20, "Detractor": 30})

        for rec in records:
            month = rec.create_date.strftime("%b")  
            if rec.voter_identification:
                data[month][rec.voter_identification] += 1

      
        months = list(calendar.month_abbr)[1:]  
        result = []
        for m in months:
            result.append({
                "month": m,
                "Promoter": data[m]["Promoter"],
                "Passive": data[m]["Passive"],
                "Detractor": data[m]["Detractor"],
            })
        return result
    
    @api.model
    def get_voters_group(self):
        record = self.env['net.promoter.score'].search([])
        promoters = record.filtered(lambda r: r.voter_identification == 'Promoter')
        passives = record.filtered(lambda r: r.voter_identification == 'Passive')
        detractors = record.filtered(lambda r: r.voter_identification == 'Detractor')
        voters = {
            'promoters': promoters,
            'passives': passives,
            'detractors': detractors,
        }
        return voters