/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

class OtmAttendanceDashboard extends Component {
    static template = "otm_attendance_reports.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        const today = new Date();
        const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);

        this.state = useState({
            period: "monthly",
            dateFrom: this._fmt(monthStart),
            dateTo: this._fmt(today),
            departmentId: false,
            departments: [],
            jobId: false,
            jobs: [],
            data: {
                counts: { late_arrival: 0, miss_punch: 0, early_leaving: 0, absent: 0, overtime: 0 },
                trend: [],
                total_employees: 0,
            },
            loading: true,
        });

        onWillStart(async () => {
            this.state.departments = await this.orm.searchRead(
                "hr.department", [], ["id", "name"]
            );
            this.state.jobs = await this.orm.searchRead(
                "hr.job", [], ["id", "name"]
            );
            await this.loadData();
        });
    }

    _fmt(d) {
        return d.toISOString().slice(0, 10);
    }

    async loadData() {
        this.state.loading = true;
        const data = await this.orm.call(
            "otm.attendance.report.engine",
            "get_dashboard_data",
            [this.state.dateFrom, this.state.dateTo],
            {
                department_id: this.state.departmentId || false,
                job_id: this.state.jobId || false,
            }
        );
        this.state.data = data;
        this.state.loading = false;
    }

    onPeriodChange(ev) {
        const period = ev.target.value;
        this.state.period = period;
        const today = new Date();
        if (period === "daily") {
            this.state.dateFrom = this._fmt(today);
            this.state.dateTo = this._fmt(today);
        } else if (period === "weekly") {
            const day = today.getDay() === 0 ? 6 : today.getDay() - 1;
            const monday = new Date(today);
            monday.setDate(today.getDate() - day);
            this.state.dateFrom = this._fmt(monday);
            this.state.dateTo = this._fmt(today);
        } else if (period === "monthly") {
            const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
            this.state.dateFrom = this._fmt(monthStart);
            this.state.dateTo = this._fmt(today);
        }
        if (period !== "custom") {
            this.loadData();
        }
    }

    onDateChange(ev, field) {
        this.state[field] = ev.target.value;
        this.state.period = "custom";
    }

    onDepartmentChange(ev) {
        this.state.departmentId = ev.target.value ? parseInt(ev.target.value) : false;
        this.loadData();
    }

    onJobChange(ev) {
        this.state.jobId = ev.target.value ? parseInt(ev.target.value) : false;
        this.loadData();
    }

    onApply() {
        this.loadData();
    }

    openReport(reportType) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "otm.attendance.report.wizard",
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
            context: {
                default_report_type: reportType,
                default_date_from: this.state.dateFrom,
                default_date_to: this.state.dateTo,
                default_department_id: this.state.departmentId,
                default_job_id: this.state.jobId,
                default_period: "custom",
            },
        });
    }

    get maxTrendValue() {
        let max = 1;
        for (const point of this.state.data.trend) {
            max = Math.max(max, point.late, point.absent);
        }
        return max;
    }

    barHeight(value) {
        return Math.round((value / this.maxTrendValue) * 100);
    }
}

registry.category("actions").add("otm_attendance_dashboard", OtmAttendanceDashboard);
