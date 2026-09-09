from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    otm_default_shift_start = fields.Float(string='Default Shift Start', default=10.0)
    otm_default_shift_end = fields.Float(string='Default Shift End', default=18.5)
    otm_default_grace_minutes = fields.Integer(string='Default Late Grace (minutes)', default=10)
    otm_default_overtime_threshold = fields.Float(
        string='Overtime Threshold (hours/day)',
        default=9.0,
        help='Worked hours beyond this in a single day count as Overtime.',
    )
