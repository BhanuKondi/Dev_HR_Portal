from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for
from models.db import db
from models.models import (
    EmployeeSalary,
    EmployeeAccount,
    PayrollRun,
    Leavee,
    Attendance,
    Holiday
)
from sqlalchemy import extract, func
import calendar
from io import BytesIO
import pdfkit
from routes.employee.employee_routes import current_employee, login_required
import inflect
config = pdfkit.configuration(wkhtmltopdf="/usr/bin/wkhtmltopdf")
manager_payroll_bp = Blueprint(
    "manager_payroll",
    __name__,
    url_prefix="/manager/payroll"
)

# -------------------------------
# Number to words
# -------------------------------
def number_to_words(n):
    p = inflect.engine()
    return p.number_to_words(n, andword="") + " rupees"

# -------------------------------
# Count Sundays
# -------------------------------
def count_sundays(year, month):
    cal = calendar.Calendar()
    return sum(
        1 for day in cal.itermonthdates(year, month)
        if day.month == month and day.weekday() == 6
    )

# -------------------------------
# Count holidays
# -------------------------------
def count_holidays(year, month):
    return Holiday.query.filter(
        extract("month", Holiday.date) == month,
        extract("year", Holiday.date) == year
    ).count()

# -------------------------------
# Payslip page
# -------------------------------
@manager_payroll_bp.route("/payslip", methods=["GET"])
@login_required
def payslip_page():
    emp = current_employee()
    if not emp:
        flash("Unauthorized access.", "danger")
        return redirect("/login")
    return render_template("manager/payslip.html", employee=emp)

# -------------------------------
# Download Payslip
# -------------------------------
@manager_payroll_bp.route("/download", methods=["POST"])
@login_required
def download_payslip():

    emp = current_employee()
    if not emp:
        flash("Unauthorized access.", "danger")
        return redirect("/login")

    pay_month = request.form.get("pay_month")
    year, month = map(int, pay_month.split("-"))

    payrun = PayrollRun.query.filter_by(
        month=month,
        year=year,
        approved=True
    ).first()

    if not payrun:
        flash("Payslip not available yet. Payroll not approved.", "warning")
        return redirect(url_for("manager_payroll.payslip_page"))

    salary = EmployeeSalary.query.filter_by(employee_id=emp.id).first()
    account = EmployeeAccount.query.filter_by(employee_id=emp.id).first()

    if not salary:
        flash("Salary details not found.", "danger")
        return redirect(url_for("manager_payroll.payslip_page"))

    # -------------------------------
    # Working days calculation
    # -------------------------------
    total_days = calendar.monthrange(year, month)[1]
    sundays = count_sundays(year, month)
    holidays = count_holidays(year, month)

    total_working_days = total_days - sundays - holidays

    # -------------------------------
    # Attendance (>= 1 hour)
    # -------------------------------
    attendance_days = db.session.query(
        func.count(func.distinct(Attendance.date))
    ).filter(
        Attendance.user_id == emp.user_id,
        extract("month", Attendance.date) == month,
        extract("year", Attendance.date) == year,
        Attendance.duration_seconds >= 1
    ).scalar() or 0

    # -------------------------------
    # Paid leaves (CL + SL)
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
    # LWP (Absent)
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
# Absent days
# -------------------------------
    absent_days = total_working_days - present_days - lwp_days
    if absent_days < 0:
        absent_days = 0  # just in case


    # -------------------------------
    # Salary calculation (based on paid days)
    # -------------------------------
    monthly_salary = float(salary.gross_salary)
    salary_per_day = round(monthly_salary / total_working_days, 2)
    net_salary = round(present_days * salary_per_day, 2)
    lwp_deduction = round(monthly_salary - net_salary, 2)

    # -------------------------------
    # Earnings breakdown
    # -------------------------------
    earnings = [
        ("Basic", salary.basic_percent),
        ("HRA", salary.hra_percent),
        ("Fixed Allowance", salary.fixed_allowance),
        ("Medical Reimbursement", salary.medical_fixed),
        ("Driver Reimbursement", salary.driver_reimbursement),
        ("EPF", salary.epf_percent)
    ]

    # -------------------------------
    # Context for PDF
    # -------------------------------
    context = {
        "company_name": "ATIKES",
        "company_address": "#4-36/1, Near Railway Station, Gopalapatnam, Andhra Pradesh 533408",
        "employee_name": f"{emp.first_name} {emp.last_name}",
        "designation": emp.job_title,
        "employee_id": emp.emp_code,
        "date_of_joining": emp.date_of_joining.strftime("%d-%m-%Y"),
        "pay_period": f"{calendar.month_name[month]} {year}",
        "pay_date": payrun.approved_at.strftime("%d-%m-%Y"),
        "bank_account": account.account_number if account else "-",
        "total_working_days": total_working_days,
        "paid_days": present_days,
        "lop_days": lwp_days,
        "earnings": earnings,
        "gross_salary": monthly_salary,
        "lwp_deduction": lwp_deduction,
        "net_pay": net_salary,
        "amount_in_words": number_to_words(net_salary),
        "basic":salary.basic_percent *100,
        "hra":salary.hra_percent,
        "fixed_allowance":salary.fixed_allowance *100,
        "absent_days":absent_days
    }

    # -------------------------------
    # Render HTML
    # -------------------------------
    rendered_html = render_template(
        "manager/payslip_pdf.html",
        **context
    )

    # -------------------------------
    # Generate PDF
    # -------------------------------
    pdf_options = {
        "page-size": "A4",
        "encoding": "UTF-8",
        "enable-local-file-access": None
    }

    pdf_bytes = pdfkit.from_string(rendered_html,False,options=pdf_options,configuration=config)

    return send_file(
        BytesIO(pdf_bytes),
        as_attachment=True,
        download_name=f"Payslip_{emp.emp_code}_{month}_{year}.pdf",
        mimetype="application/pdf"
    )