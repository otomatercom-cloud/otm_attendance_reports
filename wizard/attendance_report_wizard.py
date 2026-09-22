from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

REPORT_TYPE_LABELS = {
    'late_arrival': 'Late Arrival',
    'miss_punch': 'Miss Punch',
    'early_leaving': 'Early Leaving',
    'absent': 'Absent / LOP',
    'overtime': 'Overtime / Extra Hours',
    'summary': 'Attendance Summary',
}


class OtmAttendanceReportWizard(models.TransientModel):
    _name = 'otm.attendance.report.wizard'
    _description = 'Attendance Report Wizard'
    _rec_name = 'name'

    name = fields.Char(string='Name', compute='_compute_name')

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
    job_id = fields.Many2one('hr.job', string='Job Position',
                              help='Filter by Job Type / Designation (e.g. Tele-Caller, Academic Coordinator).')

    line_ids = fields.One2many('otm.attendance.report.line', 'wizard_id', string='Results')

    @api.depends('report_type', 'date_from', 'date_to')
    def _compute_name(self):
        for rec in self:
            label = REPORT_TYPE_LABELS.get(rec.report_type, 'Attendance Report')
            if rec.date_from and rec.date_to:
                rec.name = '%s (%s - %s)' % (
                    label,
                    rec.date_from.strftime('%d-%m-%Y'),
                    rec.date_to.strftime('%d-%m-%Y'),
                )
            else:
                rec.name = label

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
            job_id=self.job_id.id or None,
        )
        self.line_ids.unlink()
        self.env['otm.attendance.report.line'].create([{
            'wizard_id': self.id,
            'employee': r['employee'],
            'department': r['department'],
            'job': r.get('job', ''),
            'date': r['date'],
            'detail': r['detail'],
        } for r in rows])

        return {
            'type': 'ir.actions.act_window',
            'name': self.name or 'Attendance Report',
            'res_model': 'otm.attendance.report.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'current',
        }

    def action_save(self):
        """Persist the current results into a permanent Saved Report record."""
        self.ensure_one()
        if not self.line_ids:
            self.action_generate()

        saved = self.env['otm.attendance.report.saved'].create({
            'name': self.name,
            'report_type': self.report_type,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'department_id': self.department_id.id or False,
            'job_id': self.job_id.id or False,
            'source': 'manual',
        })
        self.env['otm.attendance.report.saved.line'].create([{
            'saved_id': saved.id,
            'employee': line.employee,
            'department': line.department,
            'job': line.job,
            'date': line.date,
            'detail': line.detail,
        } for line in self.line_ids])

        return {
            'type': 'ir.actions.act_window',
            'name': saved.name,
            'res_model': 'otm.attendance.report.saved',
            'res_id': saved.id,
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'current',
        }


class OtmAttendanceReportLine(models.TransientModel):
    _name = 'otm.attendance.report.line'
    _description = 'Attendance Report Result Line'

    wizard_id = fields.Many2one('otm.attendance.report.wizard', ondelete='cascade')
    employee = fields.Char(string='Employee')
    department = fields.Char(string='Department')
    job = fields.Char(string='Job Position')
    date = fields.Char(string='Date')
    detail = fields.Char(string='Detail')
