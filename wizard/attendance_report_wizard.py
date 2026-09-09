from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class OtmAttendanceReportWizard(models.TransientModel):
    _name = 'otm.attendance.report.wizard'
    _description = 'Attendance Report Wizard'

    report_type = fields.Selection([
        ('late_arrival', 'Late Arrival'),
        ('miss_punch', 'Miss Punch'),
        ('early_leaving', 'Early Leaving'),
        ('absent', 'Absent / LOP'),
        ('overtime', 'Overtime / Extra Hours'),
        ('summary', 'Attendance Summary'),
    ], string='Report', required=True, default='late_arrival')

    period = fields.Selection([
        ('daily', 'Daily (Today)'),
        ('weekly', 'Weekly (This Week)'),
        ('monthly', 'Monthly (This Month)'),
        ('custom', 'Custom Range'),
    ], string='Period', required=True, default='monthly')

    date_from = fields.Date(string='Date From', required=True,
                             default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string='Date To', required=True,
                           default=lambda self: fields.Date.context_today(self))

    employee_ids = fields.Many2many('hr.employee', string='Employees')
    department_id = fields.Many2one('hr.department', string='Department')

    line_ids = fields.One2many('otm.attendance.report.line', 'wizard_id', string='Results')

    @api.onchange('period')
    def _onchange_period(self):
        today = fields.Date.context_today(self)
        if self.period == 'daily':
            self.date_from = today
            self.date_to = today
        elif self.period == 'weekly':
            self.date_from = today - relativedelta(days=today.weekday())
            self.date_to = today
        elif self.period == 'monthly':
            self.date_from = today.replace(day=1)
            self.date_to = today

    def action_generate(self):
        self.ensure_one()
        engine = self.env['otm.attendance.report.engine']
        rows = engine.compute_report(
            self.report_type,
            fields.Date.to_string(self.date_from),
            fields.Date.to_string(self.date_to),
            employee_ids=self.employee_ids.ids or None,
            department_id=self.department_id.id or None,
        )
        self.line_ids.unlink()
        self.env['otm.attendance.report.line'].create([{
            'wizard_id': self.id,
            'employee': r['employee'],
            'department': r['department'],
            'date': r['date'],
            'detail': r['detail'],
        } for r in rows])

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'otm.attendance.report.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


class OtmAttendanceReportLine(models.TransientModel):
    _name = 'otm.attendance.report.line'
    _description = 'Attendance Report Result Line'

    wizard_id = fields.Many2one('otm.attendance.report.wizard', ondelete='cascade')
    employee = fields.Char(string='Employee')
    department = fields.Char(string='Department')
    date = fields.Char(string='Date')
    detail = fields.Char(string='Detail')
