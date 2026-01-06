from flask import Blueprint, render_template, request, redirect, url_for, flash
from models.db import db
from models.models import (
    Employee,
    Leavee,
    EmployeeSalary,
    PayrollRun,
    Holiday,
    Attendance
)
from sqlalchemy import extract, func
import calendar
from datetime import datetime

admin_payroll_bp = Blueprint(
    "admin_payroll",
    __name__,
    url_prefix="/admin/payroll"
)

# ======================================================
# PAYROLL DASHBOARD
# ======================================================
@admin_payroll_bp.route("/", methods=["GET"])
def payroll_dashboard():
    return render_template("admin/payroll.html")


# ======================================================
# GENERATE PAY RUN
# ======================================================
@admin_payroll_bp.route("/generate", methods=["POST"])
def generate_payrun():

    pay_month = request.form.get("pay_month")

    if not pay_month:
        flash("Please select payroll month.", "danger")
        return redirect(url_for("admin_payroll.payroll_dashboard"))

    year, month = map(int, pay_month.split("-"))
    days_in_month = calendar.monthrange(year, month)[1]

    # -------------------------------
    # Calculate Sundays
    # -------------------------------
    cal = calendar.Calendar()
    sundays = sum(
        1 for day in cal.itermonthdates(year, month)
        if day.month == month and day.weekday() == 6
    )

    # -------------------------------
    # Calculate Holidays
    # -------------------------------
    holidays = Holiday.query.filter(
        extract("month", Holiday.date) == month,
        extract("year", Holiday.date) == year
    ).count()

    total_working_days = days_in_month - sundays - holidays
    if total_working_days <= 0:
        total_working_days = days_in_month

    payroll_data = []

    employees = Employee.query.filter(Employee.status == "Active").all()

    for emp in employees:

        salary = EmployeeSalary.query.filter_by(employee_id=emp.id).first()
        if not salary:
            continue

        # -------------------------------
        # Attendance Days (>=5 seconds)
        # -------------------------------
        attendance_days = db.session.query(
            func.count(func.distinct(Attendance.date))
        ).filter(
            Attendance.user_id == emp.user_id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year,
            Attendance.duration_seconds >= 5
        ).scalar() or 0

        # -------------------------------
        # Paid Leaves (CL + SL)
        # -------------------------------
        paid_leave_days = db.session.query(
            func.coalesce(func.sum(Leavee.total_days), 0)
        ).filter(
            Leavee.emp_code == emp.emp_code,
            Leavee.leave_type.in_(["Casual Leave", "Sick Leave"]),
            Leavee.status == "Approved",
            extract("month", Leavee.start_date) == month,
            extract("year", Leavee.start_date) == year
        ).scalar() or 0

        present_days = int(attendance_days + paid_leave_days)

        # -------------------------------
        # LWP Days
        # -------------------------------
        lwp_days = db.session.query(
            func.coalesce(func.sum(Leavee.total_days), 0)
        ).filter(
            Leavee.emp_code == emp.emp_code,
            Leavee.leave_type == "Leave Without Pay",
            Leavee.status == "Approved",
            extract("month", Leavee.start_date) == month,
            extract("year", Leavee.start_date) == year
        ).scalar() or 0

        lwp_days = int(lwp_days)

        # -------------------------------
        # Absent Days
        # -------------------------------
        absent_days = int(paid_leave_days)
        if absent_days < 0:
            absent_days = 0

        # ======================================================
        # ✅ CORRECT SALARY CALCULATION
        # ======================================================

        annual_gross_salary = float(salary.gross_salary)

        # Monthly salary
        monthly_salary = round(annual_gross_salary / 12, 2)

        # Per day salary
        salary_per_day = round(monthly_salary / total_working_days, 2)

        # LWP deduction
        lwp_deduction = round(lwp_days * salary_per_day, 2)

        # Net salary for the month
        net_salary = round(monthly_salary - lwp_deduction, 2)
        if net_salary < 0:
            net_salary = 0

        # -------------------------------
        # Append Payroll Data
        # -------------------------------
        payroll_data.append({
            "emp_code": emp.emp_code,
            "name": f"{emp.first_name} {emp.last_name}",
            "salary_month": f"{calendar.month_name[month]} {year}",

            "total_working_days": total_working_days,
            "attendance_days": attendance_days,
            "paid_leave_days": paid_leave_days,
            "present_days": present_days,
            "lwp_days": lwp_days,
            "absent_days": absent_days,

            "annual_gross_salary": annual_gross_salary,
            "monthly_salary": monthly_salary,
            "salary_per_day": salary_per_day,
            "lwp_deduction": lwp_deduction,
            "net_salary": net_salary
        })

    # ======================================================
    # CHECK PAYROLL APPROVAL STATUS
    # ======================================================
    payrun = PayrollRun.query.filter_by(
        month=month,
        year=year
    ).first()

    payroll_approved = payrun.approved if payrun else False

    return render_template(
        "admin/payroll.html",
        payroll_data=payroll_data,
        selected_month=month,
        selected_year=year,
        payroll_approved=payroll_approved
    )


# ======================================================
# APPROVE PAY RUN
# ======================================================
@admin_payroll_bp.route("/approve", methods=["POST"])
def approve_payrun():

    month = int(request.form.get("month"))
    year = int(request.form.get("year"))

    payrun = PayrollRun.query.filter_by(
        month=month,
        year=year
    ).first()

    if not payrun:
        payrun = PayrollRun(
            month=month,
            year=year,
            approved=True,
            approved_at=datetime.utcnow()
        )
        db.session.add(payrun)
    else:
        payrun.approved = True
        payrun.approved_at = datetime.utcnow()

    db.session.commit()

    flash("Payroll approved successfully!", "success")
    return redirect(url_for("admin_payroll.payroll_dashboard"))
