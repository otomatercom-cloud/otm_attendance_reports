from odoo import api, fields, models


REPORT_TYPES = [
    ('late_arrival', 'Late Arrival'),
    ('miss_punch', 'Miss Punch'),
    ('early_leaving', 'Early Leaving'),
    ('absent', 'Absent / LOP'),
    ('overtime', 'Overtime / Extra Hours'),
    ('summary', 'Attendance Summary'),
]


class OtmAttendanceReportSaved(models.Model):
    _name = 'otm.attendance.report.saved'
    _description = 'Saved Attendance Report'
    _order = 'generated_on desc'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    report_type = fields.Selection(REPORT_TYPES, string='Report', required=True)
    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)
    department_id = fields.Many2one('hr.department', string='Department')
    job_id = fields.Many2one('hr.job', string='Job Position')
    source = fields.Selection([
        ('manual', 'Manual'),
        ('auto', 'Auto (Daily)'),
    ], string='Source', default='manual', required=True)
    generated_on = fields.Datetime(string='Generated On', default=fields.Datetime.now, required=True)
    line_ids = fields.One2many('otm.attendance.report.saved.line', 'saved_id', string='Results')
    line_count = fields.Integer(string='Rows', compute='_compute_line_count')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.model
    def _cron_generate_daily_reports(self):
        """Runs once a day: generates every report type for yesterday and
        stores the results here as a permanent history."""
        from datetime import timedelta
        yesterday = fields.Date.context_today(self) - timedelta(days=1)
        engine = self.env['otm.attendance.report.engine']
        for report_type, label in REPORT_TYPES:
            rows = engine.compute_report(
                report_type,
                fields.Date.to_string(yesterday),
                fields.Date.to_string(yesterday),
            )
            saved = self.create({
                'name': '%s - %s (Auto)' % (label, yesterday.strftime('%d-%m-%Y')),
                'report_type': report_type,
                'date_from': yesterday,
                'date_to': yesterday,
                'source': 'auto',
            })
            self.env['otm.attendance.report.saved.line'].create([{
                'saved_id': saved.id,
                'employee': r['employee'],
                'department': r['department'],
                'job': r.get('job', ''),
                'date': r['date'],
                'detail': r['detail'],
            } for r in rows])
        return True


class OtmAttendanceReportSavedLine(models.Model):
    _name = 'otm.attendance.report.saved.line'
    _description = 'Saved Attendance Report Line'

    saved_id = fields.Many2one('otm.attendance.report.saved', ondelete='cascade')
    employee = fields.Char(string='Employee')
    department = fields.Char(string='Department')
    job = fields.Char(string='Job Position')
    date = fields.Char(string='Date')
    detail = fields.Char(string='Detail')
