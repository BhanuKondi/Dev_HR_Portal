from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
from models.models import (
    Employee,
    User,
    Role,
    LeaveApprovalConfig,
    EmployeeSalary,
    EmployeeAccount
)
from models.db import db
from sqlalchemy import cast, Integer
from datetime import datetime   # ✅ REQUIRED
 
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
 
# =====================================================
# ADMIN ACCESS CHECK
# =====================================================
@admin_bp.before_request
def check_admin():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    if session.get("role_id") != 1:
        return "Access denied", 403
 
 
# =====================================================
# DASHBOARD
# =====================================================
@admin_bp.route("/dashboard")
def dashboard():
    return render_template("admin/dashboard.html")
 
 
# =====================================================
# EMPLOYEES LIST
# =====================================================
@admin_bp.route("/employees")
def employees():
    employees = Employee.query.order_by(cast(Employee.emp_code, Integer)).all()
    return render_template("admin/employees.html", employees=employees)
 
 
# =====================================================
# ADD EMPLOYEE
# =====================================================
@admin_bp.route("/employees/add", methods=["POST"])
def add_employee():
    try:
        # ---------- USER ----------
        user = User(
            email=request.form.get("work_email"),
            display_name=f"{request.form.get('first_name')} {request.form.get('last_name')}",
            role_id=int(request.form.get("role_id")),
            must_change_password=True,
            is_active=True  # ✅ IMPORTANT
        )
        user.set_password(request.form.get("password"))
        db.session.add(user)
        db.session.flush()
        manager_id=request.form.get("manager_id")
 
        # ---------- EMPLOYEE ----------
        emp = Employee(
            emp_code=request.form.get("emp_code"),
            first_name=request.form.get("first_name"),
            last_name=request.form.get("last_name"),
            work_email=request.form.get("work_email"),
            phone=request.form.get("phone"),
            department=request.form.get("department"),
            job_title=request.form.get("job_title"),
            date_of_joining=request.form.get("date_of_joining"),
            status="Active",
            user_id=user.id,
            manager_emp_id=int(manager_id) if manager_id else None
        )
        db.session.add(emp)
        db.session.flush()
 
        # ---------- SALARY ----------
        salary = EmployeeSalary(
            employee_id=emp.id,
            gross_salary=float(request.form.get("ctc", 0)),
            basic_percent=float(request.form.get("basic_percent", 50)),
            hra_percent=float(request.form.get("hra_percent", 20)),
            fixed_allowance=float(request.form.get("fixed_allowance", 4532)),
            medical_fixed=float(request.form.get("medical_fixed", 1000)),
            driver_reimbursement=float(request.form.get("driver_reimbursement", 1000)),
            epf_percent=float(request.form.get("epf_percent", 12)),
            total_deductions=0,
            net_salary=float(request.form.get("ctc", 0))
        )
        db.session.add(salary)
 
        # ---------- BANK ACCOUNT ----------
        account = EmployeeAccount(
            employee_id=emp.id,
            bank_name=request.form.get("bank_name"),
            account_number=request.form.get("account_number"),
            ifsc_code=request.form.get("ifsc_code"),
            account_holder_name=request.form.get("account_holder_name")
        )
        db.session.add(account)
 
        db.session.commit()
        flash("Employee added successfully", "success")
 
    except Exception as e:
        db.session.rollback()
        print(e)
        flash(str(e), "danger")
 
    return redirect(url_for("admin.employees"))
 
 
# =====================================================
# VIEW EMPLOYEE (JSON)
# =====================================================
@admin_bp.route("/employees/view/<int:id>")
def view_employee(id):
    emp = Employee.query.get_or_404(id)
    salary = EmployeeSalary.query.filter_by(employee_id=id).first()
    account = EmployeeAccount.query.filter_by(employee_id=id).first()
 
    return jsonify({
        "emp_code": emp.emp_code,
        "first_name": emp.first_name,
        "last_name": emp.last_name,
        "work_email": emp.work_email,
        "phone": emp.phone,
        "department": emp.department,
        "job_title": emp.job_title,
        "date_of_joining": str(emp.date_of_joining),
        "status": emp.status,  # ✅ FIXED
        "role_id": emp.user.role_id if emp.user else None,
        "role_name": emp.user.role.name if emp.user and emp.user.role else "",
        "manager_id": emp.manager_emp_id,
        "manager_name": f"{emp.manager.first_name} {emp.manager.last_name}" if emp.manager else "-",
 
        "salary": {
            "gross_salary": salary.gross_salary if salary else 0,
            "basic_percent": salary.basic_percent if salary else 0,
            "hra_percent": salary.hra_percent if salary else 0,
            "fixed_allowance": salary.fixed_allowance if salary else 0,
            "medical_fixed": salary.medical_fixed if salary else 0,
            "driver_reimbursement": salary.driver_reimbursement if salary else 0,
            "epf_percent": salary.epf_percent if salary else 0
        },
 
        "account": {
            "bank_name": account.bank_name if account else "",
            "account_number": account.account_number if account else "",
            "ifsc_code": account.ifsc_code if account else "",
            "account_holder_name": account.account_holder_name if account else ""
        }
    })
 
 
# =====================================================
# EDIT EMPLOYEE
# =====================================================
@admin_bp.route("/employees/edit/<int:id>", methods=["POST"])
def edit_employee(id):
    emp = Employee.query.get_or_404(id)
 
    # ---------- BASIC ----------
    emp.first_name = request.form.get("first_name")
    emp.last_name = request.form.get("last_name")
    emp.work_email = request.form.get("work_email")
    emp.phone = request.form.get("phone")
    emp.department = request.form.get("department")
    emp.job_title = request.form.get("job_title")
    manager_id = request.form.get("manager_emp_id")
    emp.manager_emp_id = int(manager_id) if manager_id else None
 
    # 🔥 STATUS SYNC (MOST IMPORTANT PART)
    new_status = request.form.get("status")
    emp.status = new_status
 
    user = emp.user
    if user:
        user.status = new_status
        if new_status == "Active":
            user.is_active = True
            user.status_date = None
        else:
            user.is_active = False
            user.status_date = datetime.utcnow().date()
 
    # ---------- SALARY ----------
    salary = EmployeeSalary.query.filter_by(employee_id=id).first()
    if not salary:
        salary = EmployeeSalary(employee_id=id)
        db.session.add(salary)
 
    salary.gross_salary = float(request.form.get("ctc", 0))
    salary.basic_percent = float(request.form.get("basic_percent", 50))
    salary.hra_percent = float(request.form.get("hra_percent", 20))
    salary.fixed_allowance = float(request.form.get("fixed_allowance", 4532))
    salary.medical_fixed = float(request.form.get("medical_fixed", 1000))
    salary.driver_reimbursement = float(request.form.get("driver_reimbursement", 1000))
    salary.epf_percent = float(request.form.get("epf_percent", 12))
    salary.net_salary = salary.gross_salary
 
    # ---------- ACCOUNT ----------
    account = EmployeeAccount.query.filter_by(employee_id=id).first()
    if not account:
        account = EmployeeAccount(employee_id=id)
        db.session.add(account)
 
    account.bank_name = request.form.get("bank_name")
    account.account_number = request.form.get("account_number")
    account.ifsc_code = request.form.get("ifsc_code")
    account.account_holder_name = request.form.get("account_holder_name")
 
    db.session.commit()
    flash("Employee updated successfully", "success")
    return redirect(url_for("admin.employees"))
 
 
# =====================================================
# CONFIGURE LEAVE APPROVALS
# =====================================================
@admin_bp.route("/configure-approvals", methods=["GET", "POST"])
def configure_approvals():
    users = User.query.all()
    config = LeaveApprovalConfig.query.first()
 
    if not config:
        config = LeaveApprovalConfig()
        db.session.add(config)
        db.session.commit()
 
    if request.method == "POST":
        level1 = request.form.get("level1")
        level2 = request.form.get("level2")
 
        if level1 == "MANAGER":
            config.use_manager_l1 = True
            config.level1_approver_id = None
        else:
            config.use_manager_l1 = False
            config.level1_approver_id = int(level1) if level1 else None
 
        config.level2_approver_id = int(level2) if level2 else None
 
        db.session.commit()
        flash("Approval workflow updated successfully!", "success")
        return redirect(url_for("admin.configure_approvals"))
 
    return render_template(
        "admin/configure_approvals.html",
        users=users,
        config=config
    )
 
 