'''from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from models.models import Employee, Leave, User, Holiday, db,Leavee,LeaveApprovalConfig
from datetime import datetime
from utils.email_service import send_email
from flask import Blueprint, render_template, session, redirect, flash, url_for, jsonify
from models.models import Employee
from models.attendance import Attendance, IST
from models.db import db
from datetime import datetime, date
from sqlalchemy import func
manager_lbp = Blueprint(
    "manager_leaves",
    __name__,
    url_prefix="/manager/leaves"
)
def current_employee():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return Employee.query.filter_by(user_id=user_id).first()

def get_user_email(user_id):
    user = User.query.filter_by(id=user_id).first()
    return user.email if user else None


def get_total_cl_for_year():
    return (datetime.now().month - 1) * 0.5


def get_consumed_leaves(emp_code, leave_type):
    current_year = datetime.now().year

    total = db.session.query(
        func.coalesce(func.sum(Leavee.total_days), 0.0)
    ).filter(
        Leavee.emp_code == emp_code,
        Leavee.leave_type == leave_type,
        Leavee.status == "APPROVED",
        func.extract('year', Leavee.start_date) == current_year
    ).scalar()

    return float(total)


def get_available_cl(emp_code):
    return round(get_total_cl_for_year() - get_consumed_leaves(emp_code, "Casual Leave"), 2)


def get_available_sl(emp_code):
    return round(6 - get_consumed_leaves(emp_code, "Sick Leave"), 2)


@manager_lbp.route("/leave-management")
def leave_management():
    emp = current_employee()
    if not emp:
        return redirect(url_for("auth.login"))

    holidays = Holiday.query.all()
    config = LeaveApprovalConfig.query.first()

    show_approvals_tab = False

    if config:

        # ---------------------------------------------------------
        # CASE 1: Fixed Level 1 Approver (NOT using manager)
        # ---------------------------------------------------------
        if not config.use_manager_l1 and config.level1_approver_id:
            if int(config.level1_approver_id) == emp.user_id:
                show_approvals_tab = True

        # ---------------------------------------------------------
        # CASE 2: Fixed Level 2 Approver
        # ---------------------------------------------------------
        if config.level2_approver_id:
            if int(config.level2_approver_id) == emp.user_id:
                show_approvals_tab = True

        # ---------------------------------------------------------
        # CASE 3: MANAGER-based L1 approver
        # ---------------------------------------------------------
        if config.use_manager_l1:
            # If this logged-in employee manages others
            managed_emps = Employee.query.filter_by(manager_emp_id=emp.id).all()
            if managed_emps:
                show_approvals_tab = True

    return render_template(
        "manager/leave_management.html",
        employee=emp,
        holidays=holidays,
        show_approvals_tab=show_approvals_tab
    )


@manager_lbp.route("/leave/submit", methods=["POST"])
def submit_leave():
    emp = current_employee()
    if not emp:
        return redirect(url_for("auth.login"))

    start = datetime.strptime(request.form['start_date'], "%Y-%m-%d").date()
    end = datetime.strptime(request.form['end_date'], "%Y-%m-%d").date()

    is_half_day = request.form.get("is_half_day") == "true"
    leave_type = request.form['leave_type']

    # ✅ HALF DAY FIX
    if is_half_day:
        end = start
        total_days = 0.5
    else:
        total_days = float((end - start).days + 1)

    # ❌ VALIDATION
    if is_half_day and start != end:
        flash("For half day, start and end must match", "danger")
        return redirect(url_for("manager_leaves.leave_management"))

    # ==========================================
    # LEAVE BALANCE VALIDATION
    # ==========================================

    # ==========================================
# LEAVE BALANCE VALIDATION
# ==========================================

    if leave_type == "Casual Leave":
        available = get_available_cl(emp.emp_code)

        if available <= 0:
            flash("No Casual Leave available", "danger")
            return redirect(url_for("manager_leaves.leave_management"))

        # ✅ NEW CONDITION (IMPORTANT)
        if available < 1 and not is_half_day:
            flash("Only half-day Casual Leave available. Please select Half Day.", "danger")
            return redirect(url_for("manager_leaves.leave_management"))

        if total_days > available:
            flash(f"Only {available} CL available", "danger")
            return redirect(url_for("manager_leaves.leave_management"))


    elif leave_type == "Sick Leave":
        available = get_available_sl(emp.emp_code)

        if available <= 0:
            flash("No Sick Leave available", "danger")
            return redirect(url_for("manager_leaves.leave_management"))

        # ✅ SAME FIX FOR SL (optional but recommended)
        if available < 1 and not is_half_day:
            flash("Only half-day Sick Leave available. Please select Half Day.", "danger")
            return redirect(url_for("manager_leaves.leave_management"))

        if total_days > available:
            flash(f"Only {available} SL available", "danger")
            return redirect(url_for("manager_leaves.leave_management"))

    config = LeaveApprovalConfig.query.first()

    # ==========================================
    # APPROVERS
    # ==========================================

    if config.use_manager_l1:
        if not emp.manager:
            flash("Manager not configured!", "danger")
            return redirect(url_for("manager_leaves.leave_management"))
        level1_id = emp.manager.user_id
    else:
        level1_id = int(config.level1_approver_id)

    level2_id = int(config.level2_approver_id)

    # ==========================================
    # CREATE LEAVE
    # ==========================================

    leave = Leavee(
        emp_code=emp.emp_code,
        start_date=start,
        end_date=end,
        total_days=total_days,
        reason=request.form['reason'],
        employee_name=f"{emp.first_name} {emp.last_name}",
        leave_type=leave_type,
        status="PENDING_L1",
        level1_approver_id=level1_id,
        level2_approver_id=level2_id,
        current_approver_id=level1_id
    )

    db.session.add(leave)
    db.session.commit()

    # ==========================================
    # EMAIL L1
    # ==========================================

    try:
        l1_email = get_user_email(level1_id)
        if l1_email:
            send_email(
                "New Leave Request - Approval Needed",
                [l1_email],
                f"""Employee: {emp.first_name}
Leave: {leave_type}
From: {start}
To: {end}
Days: {total_days}"""
            )
    except Exception as e:
        print("Email error:", e)

    flash("Leave submitted!", "success")
    return redirect(url_for("manager_leaves.leave_management"))



@manager_lbp.route("/leave/my-requests")
def my_requests():
    emp = current_employee()
    leaves = Leavee.query.filter_by(emp_code=emp.emp_code).all()

    return jsonify([
        {
            "id": l.id,
            "start": l.start_date.strftime("%Y-%m-%d"),
            "end": l.end_date.strftime("%Y-%m-%d"),
            "days": float(l.total_days),
            "reason": l.reason,
            "status": l.status,
            "leave_type":l.leave_type
        }
        for l in leaves
    ])
@manager_lbp.route("/leave/my-approvals")
def my_approvals():
    emp = current_employee()

    # Fetch approval config
    config = LeaveApprovalConfig.query.first()
    level1 = config.level1_approver_id
    level2 = config.level2_approver_id

    all_pending = Leavee.query.filter_by(current_approver_id=emp.user_id).all()

    final_list = []

    for l in all_pending:

        # --------------------------
        # RULE: SKIP SELF-APPROVAL
        # If employee is Level-1 approver AND leave belongs to him → skip
        # --------------------------
        if emp.user_id == level1 and l.emp_code == emp.emp_code:
            # Auto-route to Level2 instead of showing in L1 approvals
            l.current_approver_id = level2
            l.status = "PENDING_L2"
            db.session.commit()
            continue  # do NOT show in the list

        # If employee is Level2 approver AND request belongs to him → auto approve
        if emp.user_id == level2 and l.emp_code == emp.emp_code:
            l.status = "APPROVED"
            l.current_approver_id = None
            db.session.commit()
            continue  # do NOT show in approvals

        # Normal case → show in list
        final_list.append({
            "id": l.id,
            "emp_code": l.emp_code,
            "employee_name":l.employee_name,
            "start": l.start_date.strftime("%Y-%m-%d"),
            "end": l.end_date.strftime("%Y-%m-%d"),
            "days": l.total_days,
            "reason": l.reason,
            "status": l.status,
            "leave_type":l.leave_type,
            "level1_decision_date": l.level1_decision_date,
            "level2_decision_date": l.level2_decision_date,
        })

    return jsonify(final_list)

@manager_lbp.route("/leave/approve/<int:leave_id>", methods=["POST"])
def approve_leave(leave_id):
    emp = current_employee()
    leave = Leavee.query.get_or_404(leave_id)

    if leave.current_approver_id != emp.user_id:
        return jsonify({"error": "Not authorized"}), 403

    if leave.status == "PENDING_L1":
        leave.status = "PENDING_L2"
        leave.level1_decision_date = datetime.now()
        leave.current_approver_id = leave.level2_approver_id

    elif leave.status == "PENDING_L2":
        leave.status = "APPROVED"
        leave.level2_decision_date = datetime.now()
        leave.current_approver_id = None

    db.session.commit()
    return jsonify({"success": True})
@manager_lbp.route("/leave/reject/<int:leave_id>", methods=["POST"])
def reject_leave(leave_id):
    emp = current_employee()
    leave = Leavee.query.get_or_404(leave_id)

    if leave.current_approver_id != emp.user_id:
        return jsonify({"error": "Not authorized"}), 403

    if leave.status == "PENDING_L1":
        leave.status = "REJECTED_L1"
        leave.level1_decision_date = datetime.now()

    elif leave.status == "PENDING_L2":
        leave.status = "REJECTED_L2"
        leave.level2_decision_date = datetime.now()

    leave.current_approver_id = None
    db.session.commit()

    return jsonify({"success": True})
@manager_lbp.route("/leave/balance")
def leave_balance():
    emp = current_employee()

    return jsonify({
        "cl": get_available_cl(emp.emp_code),
        "sl": get_available_sl(emp.emp_code)
    })
'''
from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
from models.models import Employee, Leave, User, Holiday, db, Leavee, LeaveApprovalConfig
from sqlalchemy import func
from datetime import datetime
from utils.email_service import send_email

manager_lbp = Blueprint(
    "manager_leaves",
    __name__,
    url_prefix="/manager/leaves"
)

# ==========================================
# HELPERS
# ==========================================

def current_employee():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return Employee.query.filter_by(user_id=user_id).first()


def get_user_email(user_id):
    user = User.query.filter_by(id=user_id).first()
    return user.email if user else None

import calendar
from datetime import datetime

def get_total_cl_for_year():
    CL_START_MONTH = 3  # March

    today = datetime.now()
    current_month = today.month
    current_day = today.day

    if current_month < CL_START_MONTH:
        return 0

    # Get last day of current month
    last_day = calendar.monthrange(today.year, current_month)[1]

    # If month NOT completed → don't count this month
    if current_day < last_day:
        months_completed = current_month - CL_START_MONTH
    else:
        months_completed = current_month - CL_START_MONTH + 1

    return months_completed * 0.5


def get_consumed_leaves(emp_code, leave_type):
    current_year = datetime.now().year

    total = db.session.query(
        func.coalesce(func.sum(Leavee.total_days), 0.0)
    ).filter(
        Leavee.emp_code == emp_code,
        Leavee.leave_type == leave_type,
        Leavee.status == "APPROVED",
        func.extract('year', Leavee.start_date) == current_year
    ).scalar()

    return float(total)


def get_available_cl(emp_code):
    return round(get_total_cl_for_year() - get_consumed_leaves(emp_code, "Casual Leave"), 2)


def get_available_sl(emp_code):
    return round(6 - get_consumed_leaves(emp_code, "Sick Leave"), 2)


# ==========================================
# MAIN PAGE
# ==========================================

@manager_lbp.route("/leave-management")
def leave_management():
    emp = current_employee()
    if not emp:
        return redirect(url_for("auth.login"))

    holidays = Holiday.query.all()
    config = LeaveApprovalConfig.query.first()

    show_approvals_tab = False

    if config:
        if not config.use_manager_l1 and config.level1_approver_id:
            if int(config.level1_approver_id) == emp.user_id:
                show_approvals_tab = True

        if config.level2_approver_id:
            if int(config.level2_approver_id) == emp.user_id:
                show_approvals_tab = True

        if config.use_manager_l1:
            managed_emps = Employee.query.filter_by(manager_emp_id=emp.id).all()
            if managed_emps:
                show_approvals_tab = True

    return render_template(
        "manager/leave_management.html",
        employee=emp,
        holidays=holidays,
        show_approvals_tab=show_approvals_tab
    )


# ==========================================
# SUBMIT LEAVE
# ==========================================

@manager_lbp.route("/leave/submit", methods=["POST"])
def submit_leave():
    emp = current_employee()
    if not emp:
        return redirect(url_for("auth.login"))

    start = datetime.strptime(request.form['start_date'], "%Y-%m-%d").date()
    end = datetime.strptime(request.form['end_date'], "%Y-%m-%d").date()

    is_half_day = request.form.get("is_half_day") == "true"
    leave_type = request.form['leave_type']

    # ✅ HALF DAY FIX
    if is_half_day:
        end = start
        total_days = 0.5
    else:
        total_days = float((end - start).days + 1)

    # ❌ VALIDATION
    if is_half_day and start != end:
        flash("For half day, start and end must match", "danger")
        return redirect(url_for("manager_leaves.leave_management"))

    # ==========================================
    # LEAVE BALANCE VALIDATION
    # ==========================================

    # ==========================================
# LEAVE BALANCE VALIDATION
# ==========================================

    if leave_type == "Casual Leave":
        available = get_available_cl(emp.emp_code)

        if available <= 0:
            flash("No Casual Leave available", "danger")
            return redirect(url_for("manager_leaves.leave_management"))

        # ✅ NEW CONDITION (IMPORTANT)
        if available < 1 and not is_half_day:
            flash("Only half-day Casual Leave available. Please select Half Day.", "danger")
            return redirect(url_for("manager_leaves.leave_management"))

        if total_days > available:
            flash(f"Only {available} CL available", "danger")
            return redirect(url_for("manager_leaves.leave_management"))


    elif leave_type == "Sick Leave":
        available = get_available_sl(emp.emp_code)

        if available <= 0:
            flash("No Sick Leave available", "danger")
            return redirect(url_for("manager_leaves.leave_management"))

        # ✅ SAME FIX FOR SL (optional but recommended)
        if available < 1 and not is_half_day:
            flash("Only half-day Sick Leave available. Please select Half Day.", "danger")
            return redirect(url_for("manager_leaves.leave_management"))

        if total_days > available:
            flash(f"Only {available} SL available", "danger")
            return redirect(url_for("manager_leaves.leave_management"))

    config = LeaveApprovalConfig.query.first()

    # ==========================================
    # APPROVERS
    # ==========================================

    if config.use_manager_l1:
        if not emp.manager:
            flash("Manager not configured!", "danger")
            return redirect(url_for("manager_leaves.leave_management"))
        level1_id = emp.manager.user_id
    else:
        level1_id = int(config.level1_approver_id)

    level2_id = int(config.level2_approver_id)

    # ==========================================
    # CREATE LEAVE
    # ==========================================

    leave = Leavee(
        emp_code=emp.emp_code,
        start_date=start,
        end_date=end,
        total_days=total_days,
        reason=request.form['reason'],
        employee_name=f"{emp.first_name} {emp.last_name}",
        leave_type=leave_type,
        status="PENDING_L1",
        level1_approver_id=level1_id,
        level2_approver_id=level2_id,
        current_approver_id=level1_id
    )

    db.session.add(leave)
    db.session.commit()

    # ==========================================
    # EMAIL L1
    # ==========================================

    try:
        l1_email = get_user_email(level1_id)
        if l1_email:
            send_email(
    "New Leave Request - Action Required",
    [l1_email],
    f"""
Hello,

A new leave request has been submitted and requires your approval.

Employee Name : {emp.first_name} {emp.last_name}
Leave Type    : {leave_type}
From Date     : {start}
To Date       : {end}
Total Days    : {total_days}
Reason        : {request.form['reason']}

Please open the below link to review the request.
http://74.249.73.140:5050/manager/leaves/leave-management
Regards,  
HR System
"""
)
    except Exception as e:
        print("Email error:", e)

    flash("Leave submitted!", "success")
    return redirect(url_for("manager_leaves.leave_management"))


# ==========================================
# MY REQUESTS
# ==========================================
@manager_lbp.route("/leave/my-approvals")
def my_approvals():
    emp = current_employee()

    # Fetch approval config
    config = LeaveApprovalConfig.query.first()
    level1 = config.level1_approver_id
    level2 = config.level2_approver_id

    all_pending = Leavee.query.filter_by(current_approver_id=emp.user_id).all()

    final_list = []

    for l in all_pending:

        # --------------------------
        # RULE: SKIP SELF-APPROVAL
        # If employee is Level-1 approver AND leave belongs to him → skip
        # --------------------------
        if emp.user_id == level1 and l.emp_code == emp.emp_code:
            # Auto-route to Level2 instead of showing in L1 approvals
            l.current_approver_id = level2
            l.status = "PENDING_L2"
            db.session.commit()
            continue  # do NOT show in the list

        # If employee is Level2 approver AND request belongs to him → auto approve
        if emp.user_id == level2 and l.emp_code == emp.emp_code:
            l.status = "APPROVED"
            l.current_approver_id = None
            db.session.commit()
            continue  # do NOT show in approvals

        # Normal case → show in list
        final_list.append({
            "id": l.id,
            "emp_code": l.emp_code,
            "employee_name":l.employee_name,
            "start": l.start_date.strftime("%Y-%m-%d"),
            "end": l.end_date.strftime("%Y-%m-%d"),
            "days": l.total_days,
            "reason": l.reason,
            "status": l.status,
            "leave_type":l.leave_type,
            "level1_decision_date": l.level1_decision_date,
            "level2_decision_date": l.level2_decision_date,
        })

    return jsonify(final_list)


@manager_lbp.route("/leave/my-requests")
def my_requests():
    emp = current_employee()

    leaves = Leavee.query.filter_by(emp_code=emp.emp_code).all()

    return jsonify([
        {
            "id": l.id,
            "start": l.start_date.strftime("%Y-%m-%d"),
            "end": l.end_date.strftime("%Y-%m-%d"),
            "days": float(l.total_days),  # ✅ FIXED
            "reason": l.reason,
            "status": l.status,
            "leave_type": l.leave_type
        }
        for l in leaves
    ])


# ==========================================
# APPROVE
# ==========================================

@manager_lbp.route("/leave/approve/<int:leave_id>", methods=["POST"])
def approve_leave(leave_id):
    emp = current_employee()
    leave = Leavee.query.get_or_404(leave_id)

    if leave.current_approver_id != emp.user_id:
        return jsonify({"error": "Not authorized"}), 403

    # ============================
    # L1 APPROVAL → SEND TO L2
    # ============================
    if leave.status == "PENDING_L1":
        leave.status = "PENDING_L2"
        leave.level1_decision_date = datetime.now()
        leave.current_approver_id = leave.level2_approver_id

        # ✅ SEND EMAIL TO L2
        try:
            l2_email = get_user_email(leave.level2_approver_id)
            if l2_email:
                send_email(
    "Leave Request Pending - Level 2 Approval",
    [l2_email],
    f"""
Hello,

A leave request has been approved by Level 1 and is now pending your approval.

Employee Name : {leave.employee_name}
Leave Type    : {leave.leave_type}
From Date     : {leave.start_date}
To Date       : {leave.end_date}
Total Days    : {leave.total_days}
Reason        : {leave.reason}

Kindly open the below link to review and take appropriate action.
http://74.249.73.140:5050/manager/leaves/leave-management

Regards,  
HR System
"""
)
        except Exception as e:
            print("Email error (L2):", e)

    # ============================
    # L2 APPROVAL → FINAL APPROVED
    # ============================
    elif leave.status == "PENDING_L2":
        leave.status = "APPROVED"
        leave.level2_decision_date = datetime.now()
        leave.current_approver_id = None

        # ✅ SEND EMAIL TO EMPLOYEE
        try:
            emp_record = Employee.query.filter_by(emp_code=leave.emp_code).first()
            emp_email = get_user_email(emp_record.user_id)

            if emp_email:
             send_email(
    "Leave Approved",
    [emp_email],
    f"""
Hello,

Your leave request has been approved successfully.

Leave Details:
---------------
Leave Type : {leave.leave_type}
From       : {leave.start_date}
To         : {leave.end_date}
Days       : {leave.total_days}

Enjoy your time off 😊

Regards,  
HR Team
"""
)
        except Exception as e:
            print("Email error (Approval):", e)

    db.session.commit()
    return jsonify({"success": True})

# ==========================================
# REJECT
# ==========================================

@manager_lbp.route("/leave/reject/<int:leave_id>", methods=["POST"])
def reject_leave(leave_id):
    emp = current_employee()
    leave = Leavee.query.get_or_404(leave_id)

    if leave.current_approver_id != emp.user_id:
        return jsonify({"error": "Not authorized"}), 403

    if leave.status == "PENDING_L1":
        leave.status = "REJECTED_L1"
        leave.level1_decision_date = datetime.now()

    elif leave.status == "PENDING_L2":
        leave.status = "REJECTED_L2"
        leave.level2_decision_date = datetime.now()

    leave.current_approver_id = None
    db.session.commit()

    # ✅ SEND EMAIL TO EMPLOYEE
    try:
        emp_record = Employee.query.filter_by(emp_code=leave.emp_code).first()
        emp_email = get_user_email(emp_record.user_id)

        if emp_email:
            send_email(
    "Leave Request Rejected",
    [emp_email],
    f"""
Hello,

We regret to inform you that your leave request has been rejected.

Leave Details:
---------------
Leave Type : {leave.leave_type}
From       : {leave.start_date}
To         : {leave.end_date}
Days       : {leave.total_days}
Status     : {leave.status}

For more details, please contact your manager.

Regards,  
HR Team
"""
)
    except Exception as e:
        print("Email error (Reject):", e)

    return jsonify({"success": True})

# ==========================================
# LEAVE BALANCE
# ==========================================

@manager_lbp.route("/leave/balance")
def leave_balance():
    emp = current_employee()

    return jsonify({
        "cl": get_available_cl(emp.emp_code),
        "sl": get_available_sl(emp.emp_code)
    })