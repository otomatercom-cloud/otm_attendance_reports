from datetime import datetime, timedelta, time

import pytz

from odoo import api, models


def float_to_time(value):
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    return time(hour=hours % 24, minute=minutes % 60)


class OtmAttendanceReportEngine(models.AbstractModel):
    """Core computation engine for all attendance reports and the dashboard.
    Reads directly from standard hr.attendance (check_in / check_out), so it
    works whether attendance was punched via biometric bridge, web, or app.
    """
    _name = 'otm.attendance.report.engine'
    _description = 'Otomater Attendance Report Engine'

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------

    def _get_employee_shift(self, employee):
        company = employee.company_id or self.env.company
        start = employee.otm_shift_start or company.otm_default_shift_start
        end = employee.otm_shift_end or company.otm_default_shift_end
        grace = employee.otm_grace_minutes or company.otm_default_grace_minutes
        overtime_threshold = company.otm_default_overtime_threshold
        return start, end, grace, overtime_threshold

    def _tz(self, employee):
        tz_name = employee.tz or self.env.company.resource_calendar_id.tz or 'Asia/Kolkata'
        try:
            return pytz.timezone(tz_name)
        except Exception:
            return pytz.timezone('Asia/Kolkata')

    def _is_working_day(self, employee, day):
        calendar = employee.resource_calendar_id
        if calendar:
            attendances = calendar.attendance_ids.filtered(
                lambda a: int(a.dayofweek) == day.weekday()
            )
            return bool(attendances)
        # Fallback: Monday(0)-Saturday(5) working, Sunday(6) off
        return day.weekday() != 6

    def _is_on_leave(self, employee, day):
        Leave = self.env.get('hr.leave')
        if Leave is None:
            return False
        try:
            leaves = Leave.sudo().search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'validate'),
                ('date_from', '<=', datetime.combine(day, time.max)),
                ('date_to', '>=', datetime.combine(day, time.min)),
            ], limit=1)
            return bool(leaves)
        except Exception:
            return False

    def _daterange(self, date_from, date_to):
        day = date_from
        while day <= date_to:
            yield day
            day += timedelta(days=1)

    # ---------------------------------------------------------------
    # Main report computation
    # ---------------------------------------------------------------

    @api.model
    def compute_report(self, report_type, date_from, date_to,
                        employee_ids=None, department_id=None):
        """Returns a list of dicts, one row per finding, for the given
        report_type in ('late_arrival', 'miss_punch', 'early_leaving',
        'absent', 'overtime', 'summary')."""
        date_from = fields_to_date(date_from)
        date_to = fields_to_date(date_to)

        domain = [('active', '=', True)]
        if employee_ids:
            domain.append(('id', 'in', employee_ids))
        if department_id:
            domain.append(('department_id', '=', department_id))
        employees = self.env['hr.employee'].search(domain)

        rows = []
        for employee in employees:
            start_f, end_f, grace, ot_threshold = self._get_employee_shift(employee)
            shift_start_t = float_to_time(start_f)
            shift_end_t = float_to_time(end_f)
            tz = self._tz(employee)

            present_days = 0
            working_days = 0
            late_days = 0
            absent_days = 0

            for day in self._daterange(date_from, date_to):
                if not self._is_working_day(employee, day):
                    continue
                working_days += 1

                day_start_utc = tz.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
                day_end_utc = tz.localize(datetime.combine(day, time.max)).astimezone(pytz.utc).replace(tzinfo=None)

                attendances = self.env['hr.attendance'].sudo().search([
                    ('employee_id', '=', employee.id),
                    ('check_in', '>=', day_start_utc),
                    ('check_in', '<=', day_end_utc),
                ], order='check_in asc')

                if not attendances:
                    if self._is_on_leave(employee, day):
                        continue
                    absent_days += 1
                    if report_type == 'absent':
                        rows.append({
                            'employee': employee.name,
                            'department': employee.department_id.name or '',
                            'date': day.strftime('%d-%m-%Y'),
                            'detail': 'No attendance recorded',
                        })
                    continue

                present_days += 1
                first_in = attendances[0].check_in
                last_out = attendances[-1].check_out
                first_in_local = pytz.utc.localize(first_in).astimezone(tz)

                # Late arrival
                shift_start_dt = tz.localize(datetime.combine(day, shift_start_t))
                late_minutes = int((first_in_local - shift_start_dt).total_seconds() / 60)
                if late_minutes > grace:
                    late_days += 1
                    if report_type == 'late_arrival':
                        rows.append({
                            'employee': employee.name,
                            'department': employee.department_id.name or '',
                            'date': day.strftime('%d-%m-%Y'),
                            'detail': 'Checked in at %s (%d min late)' % (
                                first_in_local.strftime('%H:%M'), late_minutes),
                        })

                # Miss punch: has check-in but no check-out on a past day
                if not last_out and day < datetime.now(tz).date():
                    if report_type == 'miss_punch':
                        rows.append({
                            'employee': employee.name,
                            'department': employee.department_id.name or '',
                            'date': day.strftime('%d-%m-%Y'),
                            'detail': 'Checked in at %s, no check-out found' % (
                                first_in_local.strftime('%H:%M')),
                        })

                # Early leaving
                if last_out:
                    last_out_local = pytz.utc.localize(last_out).astimezone(tz)
                    shift_end_dt = tz.localize(datetime.combine(day, shift_end_t))
                    early_minutes = int((shift_end_dt - last_out_local).total_seconds() / 60)
                    if early_minutes > grace:
                        if report_type == 'early_leaving':
                            rows.append({
                                'employee': employee.name,
                                'department': employee.department_id.name or '',
                                'date': day.strftime('%d-%m-%Y'),
                                'detail': 'Checked out at %s (%d min early)' % (
                                    last_out_local.strftime('%H:%M'), early_minutes),
                            })

                # Overtime
                worked_hours = sum(attendances.mapped('worked_hours'))
                if worked_hours > ot_threshold:
                    if report_type == 'overtime':
                        rows.append({
                            'employee': employee.name,
                            'department': employee.department_id.name or '',
                            'date': day.strftime('%d-%m-%Y'),
                            'detail': '%.2f hrs worked (%.2f hrs extra)' % (
                                worked_hours, worked_hours - ot_threshold),
                        })

            if report_type == 'summary':
                pct = round((present_days / working_days) * 100, 1) if working_days else 0.0
                rows.append({
                    'employee': employee.name,
                    'department': employee.department_id.name or '',
                    'date': '%s to %s' % (date_from.strftime('%d-%m-%Y'), date_to.strftime('%d-%m-%Y')),
                    'detail': 'Present %d / %d working days (%.1f%%), Late %d, Absent %d' % (
                        present_days, working_days, pct, late_days, absent_days),
                })

        return rows

    # ---------------------------------------------------------------
    # Dashboard aggregate data
    # ---------------------------------------------------------------

    @api.model
    def get_dashboard_data(self, date_from, date_to, department_id=None):
        counts = {'late_arrival': 0, 'miss_punch': 0, 'early_leaving': 0,
                  'absent': 0, 'overtime': 0}
        for key in counts:
            counts[key] = len(self.compute_report(key, date_from, date_to,
                                                    department_id=department_id))

        date_from_d = fields_to_date(date_from)
        date_to_d = fields_to_date(date_to)
        trend = []
        for day in self._daterange(date_from_d, date_to_d):
            d_str = day.strftime('%Y-%m-%d')
            late = self.compute_report('late_arrival', d_str, d_str, department_id=department_id)
            absent = self.compute_report('absent', d_str, d_str, department_id=department_id)
            trend.append({
                'date': day.strftime('%d-%b'),
                'late': len(late),
                'absent': len(absent),
            })

        total_employees = self.env['hr.employee'].search_count([('active', '=', True)])

        return {
            'counts': counts,
            'trend': trend,
            'total_employees': total_employees,
        }


def fields_to_date(value):
    if isinstance(value, str):
        return datetime.strptime(value[:10], '%Y-%m-%d').date()
    if hasattr(value, 'date'):
        return value.date()
    return value
