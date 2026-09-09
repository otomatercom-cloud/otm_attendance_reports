from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    otm_shift_start = fields.Float(
        string='Shift Start Time',
        help='Expected shift start time (24h, e.g. 10.00 = 10:00 AM). '
             'Leave empty to use the company default set in Settings.',
    )
    otm_shift_end = fields.Float(
        string='Shift End Time',
        help='Expected shift end time (24h, e.g. 18.50 = 6:30 PM). '
             'Leave empty to use the company default set in Settings.',
    )
    otm_grace_minutes = fields.Integer(
        string='Late Grace Period (minutes)',
        help='Minutes of grace allowed after Shift Start before an arrival '
             'is counted as Late. Leave 0 to use the company default.',
    )
