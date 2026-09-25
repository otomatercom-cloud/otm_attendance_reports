import base64
import io

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class OtmAttendanceRecordWizard(models.TransientModel):
    """Raw attendance-punch report matching the standard 'All Attendances'
    list (Employee / Check In / Check Out / Worked Hours / Late Arrival /
    Late By (Hours) / Left Early / Left Early By (Hours)), filterable by
    date range, Employee, Department and Job Position."""
    _name = 'otm.attendance.record.wizard'
    _description = 'Attendance Records Report Wizard'
    _rec_name = 'name'

    name = fields.Char(string='Name', compute='_compute_name')

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
    job_id = fields.Many2one('hr.job', string='Job Position')

    line_ids = fields.One2many('otm.attendance.record.line', 'wizard_id', string='Results')

    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for rec in self:
            if rec.date_from and rec.date_to:
                rec.name = 'Attendance Records (%s - %s)' % (
                    rec.date_from.strftime('%d-%m-%Y'), rec.date_to.strftime('%d-%m-%Y'))
            else:
                rec.name = 'Attendance Records'

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
        rows = engine.compute_attendance_log(
            fields.Date.to_string(self.date_from),
            fields.Date.to_string(self.date_to),
            employee_ids=self.employee_ids.ids or None,
            department_id=self.department_id.id or None,
            job_id=self.job_id.id or None,
        )
        self.line_ids.unlink()
        self.env['otm.attendance.record.line'].create([{
            'wizard_id': self.id,
            'employee': r['employee'],
            'department': r['department'],
            'job': r['job'],
            'check_in': r['check_in'],
            'check_out': r['check_out'],
            'worked_hours': r['worked_hours'],
            'late_arrival': r['late_arrival'],
            'late_by_hours': r['late_by_hours'],
            'left_early': r['left_early'],
            'left_early_by_hours': r['left_early_by_hours'],
        } for r in rows])

        return {
            'type': 'ir.actions.act_window',
            'name': self.name or 'Attendance Records',
            'res_model': 'otm.attendance.record.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'current',
        }

    def action_export_excel(self):
        """Exports the currently generated results (or generates them first
        if the report hasn't been run yet) as a real .xlsx file, via a
        temporary ir.attachment + direct-download URL."""
        self.ensure_one()
        if not self.line_ids:
            self.action_generate()

        import xlsxwriter

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Attendance Records')

        title_format = workbook.add_format({'bold': True, 'font_size': 14})
        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#4472C4', 'font_color': 'white',
            'border': 1, 'align': 'center', 'valign': 'vcenter',
        })
        cell_format = workbook.add_format({'border': 1})
        cell_format_center = workbook.add_format({'border': 1, 'align': 'center'})

        sheet.merge_range(0, 0, 0, 9, self.name or 'Attendance Records', title_format)

        headers = [
            'Employee', 'Department', 'Job Position', 'Check In', 'Check Out',
            'Worked Hours', 'Late Arrival', 'Late By (Hours)', 'Left Early',
            'Left Early By (Hours)',
        ]
        header_row = 2
        for col, label in enumerate(headers):
            sheet.write(header_row, col, label, header_format)

        for row_idx, line in enumerate(self.line_ids, start=header_row + 1):
            sheet.write(row_idx, 0, line.employee or '', cell_format)
            sheet.write(row_idx, 1, line.department or '', cell_format)
            sheet.write(row_idx, 2, line.job or '', cell_format)
            sheet.write(row_idx, 3, line.check_in or '', cell_format)
            sheet.write(row_idx, 4, line.check_out or '', cell_format)
            sheet.write(row_idx, 5, line.worked_hours or '', cell_format_center)
            sheet.write(row_idx, 6, line.late_arrival or '', cell_format_center)
            sheet.write(row_idx, 7, line.late_by_hours or '', cell_format_center)
            sheet.write(row_idx, 8, line.left_early or '', cell_format_center)
            sheet.write(row_idx, 9, line.left_early_by_hours or '', cell_format_center)

        widths = [22, 18, 18, 18, 18, 13, 13, 15, 12, 17]
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width)
        sheet.freeze_panes(header_row + 1, 0)

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': '%s.xlsx' % (self.name or 'Attendance Records'),
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        output.close()

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }


class OtmAttendanceRecordLine(models.TransientModel):
    _name = 'otm.attendance.record.line'
    _description = 'Attendance Record Result Line'

    wizard_id = fields.Many2one('otm.attendance.record.wizard', ondelete='cascade')
    employee = fields.Char(string='Employee')
    department = fields.Char(string='Department')
    job = fields.Char(string='Job Position')
    check_in = fields.Char(string='Check In')
    check_out = fields.Char(string='Check Out')
    worked_hours = fields.Char(string='Worked Hours')
    late_arrival = fields.Char(string='Late Arrival')
    late_by_hours = fields.Char(string='Late By (Hours)')
    left_early = fields.Char(string='Left Early')
    left_early_by_hours = fields.Char(string='Left Early By (Hours)')
