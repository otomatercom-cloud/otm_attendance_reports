{
    'name': 'Otomater Attendance Reports & Dashboard',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Late Arrival, Miss Punch, Early Leaving, Absent, Overtime reports with a SaaS-style dashboard',
    'description': """
Otomater Attendance Reports & Dashboard
========================================
Adds a reporting layer on top of standard Odoo Attendance (hr.attendance):

- Late Arrival report
- Miss Punch report (single punch / no check-out)
- Early Leaving report
- Absent / LOP report
- Overtime / Extra Hours report
- Attendance Summary (Present / Absent / Leave %)

All reports support Daily / Weekly / Monthly grouping and a custom date range,
filterable by Employee / Department / Branch (Work Location).

Includes a SaaS-style dashboard (stat cards + charts) accessible from the
Attendance Reports menu.

Shift timing is configurable per employee (Shift Start / Shift End / Grace
Minutes) under each Employee's HR Settings tab, with company-wide defaults
in Settings > Attendance Reports.
    """,
    'author': 'Otomater',
    'website': 'https://otomater.com',
    'license': 'OPL-1',
    'depends': ['hr_attendance', 'hr', 'resource'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'views/attendance_report_views.xml',
        'views/attendance_report_saved_views.xml',
        'views/dashboard_views.xml',
        'views/menu_views.xml',
        'data/ir_cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'otm_attendance_reports/static/src/js/attendance_dashboard.js',
            'otm_attendance_reports/static/src/xml/attendance_dashboard.xml',
            'otm_attendance_reports/static/src/scss/attendance_dashboard.scss',
        ],
    },
    'installable': True,
    'application': True,
}
