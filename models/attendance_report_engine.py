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

    Performance note: all report types and the dashboard trend are computed
    from TWO bulk queries (hr.attendance + hr.leave) fetched once for every
    employee/date in scope, then processed in Python. Older versions of this
    engine issued a separate search() per employee per day, which meant a
    monthly report for a normal-sized team could fire thousands of tiny
    queries and take a long time to open. Never reintroduce a search() call
    inside the per-employee/per-day loop below.
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

    def _daterange(self, date_from, date_to):
        day = date_from
        while day <= date_to:
            yield day
            day += timedelta(days=1)

    # ---------------------------------------------------------------
    # Bulk computation (single pass, no per-day/per-employee queries)
    # ---------------------------------------------------------------

    def _compute_all(self, date_from, date_to, employee_ids=None, department_id=None,
                      job_id=None, want_trend=False):
        date_from = fields_to_date(date_from)
        date_to = fields_to_date(date_to)

        domain = [('active', '=', True)]
        if employee_ids:
            domain.append(('id', 'in', employee_ids))
        if department_id:
            domain.append(('department_id', '=', department_id))
        if job_id:
            domain.append(('job_id', '=', job_id))
        employees = self.env['hr.employee'].search(domain)

        result = {
            'late_arrival': [], 'miss_punch': [], 'early_leaving': [],
            'absent': [], 'overtime': [], 'summary': [],
        }
        trend_by_day = {}
        if want_trend:
            for day in self._daterange(date_from, date_to):
                trend_by_day[day] = {'late': 0, 'absent': 0}

        if not employees:
            return result, trend_by_day

        # One bulk attendance fetch for the whole range/team, with a 1-day
        # buffer either side so no record is lost to a timezone shift.
        buffer_start = datetime.combine(date_from - timedelta(days=1), time.min)
        buffer_end = datetime.combine(date_to + timedelta(days=1), time.max)
        all_attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('check_in', '>=', buffer_start),
            ('check_in', '<=', buffer_end),
        ], order='check_in asc')

        attendances_by_employee = {}
        for att in all_attendances:
            emp_id = att.employee_id.id
            attendances_by_employee.setdefault(emp_id, self.env['hr.attendance'].sudo())
            attendances_by_employee[emp_id] |= att

        # One bulk leave fetch for the whole range/team.
        leaves_by_employee = {}
        Leave = self.env.get('hr.leave')
        if Leave is not None:
            try:
                all_leaves = Leave.sudo().search([
                    ('employee_id', 'in', employees.ids),
                    ('state', '=', 'validate'),
                    ('date_from', '<=', datetime.combine(date_to, time.max)),
                    ('date_to', '>=', datetime.combine(date_from, time.min)),
                ])
                for lv in all_leaves:
                    lf = lv.date_from.date() if hasattr(lv.date_from, 'date') else lv.date_from
                    lt = lv.date_to.date() if hasattr(lv.date_to, 'date') else lv.date_to
                    leaves_by_employee.setdefault(lv.employee_id.id, []).append((lf, lt))
            except Exception:
                pass

        for employee in employees:
            start_f, end_f, grace, ot_threshold = self._get_employee_shift(employee)
            shift_start_t = float_to_time(start_f)
            shift_end_t = float_to_time(end_f)
            tz = self._tz(employee)

            # Bucket this employee's attendances by local calendar date.
            by_date = {}
            for att in attendances_by_employee.get(employee.id, self.env['hr.attendance']):
                local_date = pytz.utc.localize(att.check_in).astimezone(tz).date()
                by_date.setdefault(local_date, self.env['hr.attendance'].sudo())
                by_date[local_date] |= att

            emp_leaves = leaves_by_employee.get(employee.id, [])

            def on_leave(day, _ranges=emp_leaves):
                for lf, lt in _ranges:
                    if lf <= day <= lt:
                        return True
                return False

            present_days = 0
            working_days = 0
            late_days = 0
            absent_days = 0
            emp_name = employee.name
            dept_name = employee.department_id.name or ''
            job_name = employee.job_id.name or ''

            for day in self._daterange(date_from, date_to):
                if not self._is_working_day(employee, day):
                    continue
                working_days += 1

                attendances = by_date.get(day)
                if not attendances:
                    if on_leave(day):
                        continue
                    absent_days += 1
                    result['absent'].append({
                        'employee': emp_name,
                        'department': dept_name,
                        'job': job_name,
                        'date': day.strftime('%d-%m-%Y'),
                        'detail': 'No attendance recorded',
                    })
                    if want_trend:
                        trend_by_day[day]['absent'] += 1
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
                    result['late_arrival'].append({
                        'employee': emp_name,
                        'department': dept_name,
                        'job': job_name,
                        'date': day.strftime('%d-%m-%Y'),
                        'detail': 'Checked in at %s (%d min late)' % (
                            first_in_local.strftime('%H:%M'), late_minutes),
                    })
                    if want_trend:
                        trend_by_day[day]['late'] += 1

                # Miss punch: has check-in but no check-out on a past day
                if not last_out and day < datetime.now(tz).date():
                    result['miss_punch'].append({
                        'employee': emp_name,
                        'department': dept_name,
                        'job': job_name,
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
                        result['early_leaving'].append({
                            'employee': emp_name,
                            'department': dept_name,
                            'job': job_name,
                            'date': day.strftime('%d-%m-%Y'),
                            'detail': 'Checked out at %s (%d min early)' % (
                                last_out_local.strftime('%H:%M'), early_minutes),
                        })

                # Overtime
                worked_hours = sum(attendances.mapped('worked_hours'))
                if worked_hours > ot_threshold:
                    result['overtime'].append({
                        'employee': emp_name,
                        'department': dept_name,
                        'job': job_name,
                        'date': day.strftime('%d-%m-%Y'),
                        'detail': '%.2f hrs worked (%.2f hrs extra)' % (
                            worked_hours, worked_hours - ot_threshold),
                    })

            pct = round((present_days / working_days) * 100, 1) if working_days else 0.0
            result['summary'].append({
                'employee': emp_name,
                'department': dept_name,
                'job': job_name,
                'date': '%s to %s' % (date_from.strftime('%d-%m-%Y'), date_to.strftime('%d-%m-%Y')),
                'detail': 'Present %d / %d working days (%.1f%%), Late %d, Absent %d' % (
                    present_days, working_days, pct, late_days, absent_days),
            })

        trend = []
        if want_trend:
            for day in self._daterange(date_from, date_to):
                trend.append({
                    'date': day.strftime('%d-%b'),
                    'late': trend_by_day[day]['late'],
                    'absent': trend_by_day[day]['absent'],
                })

        return result, trend

    # ---------------------------------------------------------------
    # Public API (unchanged signatures — callers/wizard/dashboard JS
    # don't need to change)
    # ---------------------------------------------------------------

    @api.model
    def compute_report(self, report_type, date_from, date_to,
                        employee_ids=None, department_id=None, job_id=None):
        """Returns a list of dicts, one row per finding, for the given
        report_type in ('late_arrival', 'miss_punch', 'early_leaving',
        'absent', 'overtime', 'summary'). job_id filters by Job Position
        (Designation), e.g. Tele-Caller, Academic Coordinator."""
        result, _trend = self._compute_all(
            date_from, date_to, employee_ids=employee_ids,
            department_id=department_id, job_id=job_id, want_trend=False,
        )
        return result.get(report_type, [])

    @api.model
    def get_dashboard_data(self, date_from, date_to, department_id=None, job_id=None):
        result, trend = self._compute_all(
            date_from, date_to, department_id=department_id, job_id=job_id, want_trend=True,
        )
        counts = {
            key: len(result[key])
            for key in ('late_arrival', 'miss_punch', 'early_leaving', 'absent', 'overtime')
        }

        emp_domain = [('active', '=', True)]
        if department_id:
            emp_domain.append(('department_id', '=', department_id))
        if job_id:
            emp_domain.append(('job_id', '=', job_id))
        total_employees = self.env['hr.employee'].search_count(emp_domain)

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
