from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    otm_default_shift_start = fields.Float(
        related='company_id.otm_default_shift_start', readonly=False)
    otm_default_shift_end = fields.Float(
        related='company_id.otm_default_shift_end', readonly=False)
    otm_default_grace_minutes = fields.Integer(
        related='company_id.otm_default_grace_minutes', readonly=False)
    otm_default_overtime_threshold = fields.Float(
        related='company_id.otm_default_overtime_threshold', readonly=False)
