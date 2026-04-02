from datetime import datetime
from .db import db
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.dialects.mysql import INTEGER, BIGINT, VARCHAR, TEXT
import uuid

# ------------------- Roles -------------------
class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(INTEGER, primary_key=True)
    name = db.Column(VARCHAR(100), unique=True, nullable=False)


# ------------------- Users -------------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(INTEGER, primary_key=True)
    email = db.Column(VARCHAR(255), unique=True, nullable=False)
    password_hash = db.Column(VARCHAR(255), nullable=False)
    display_name = db.Column(VARCHAR(255))
    profile_photo_path = db.Column(VARCHAR(255), nullable=True)

    role_id = db.Column(INTEGER, db.ForeignKey("roles.id"), nullable=False)
    role = db.relationship("Role")

    is_active = db.Column(db.Boolean, default=True)
    must_change_password = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # 1-to-1 Employee Profile
    employee = db.relationship("Employee", back_populates="user", uselist=False)

    # 👇 ADD THIS: Link Attendance to User
    attendance_records = db.relationship("Attendance", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# ------------------- Employees -------------------
class Employee(db.Model):
    __tablename__ = "employees"
    id = db.Column(INTEGER, primary_key=True)
    emp_code = db.Column(VARCHAR(50), unique=True, nullable=False)

    user_id = db.Column(INTEGER, db.ForeignKey("users.id"))
    user = db.relationship("User", back_populates="employee")

    first_name = db.Column(VARCHAR(100), nullable=False)
    last_name = db.Column(VARCHAR(100), nullable=False)
    work_email = db.Column(VARCHAR(255), unique=True, nullable=False)
    phone = db.Column(VARCHAR(20))
    address = db.Column(TEXT)
    date_of_joining = db.Column(db.Date, nullable=False)

    manager_emp_id = db.Column(INTEGER, db.ForeignKey("employees.id"))
    manager = db.relationship(
    "Employee",
    remote_side=[id],
    backref="team_members"
)

    status = db.Column(VARCHAR(50), default="Active")
    department = db.Column(VARCHAR(100))
    job_title = db.Column(VARCHAR(100))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    salary = db.relationship("EmployeeSalary", backref="employee", uselist=False)
    account = db.relationship("EmployeeAccount", backref="employee", uselist=False)

    # 👇 OPTIONAL — only if you want attendance per employee also
    #attendance_records = db.relationship("Attendance", backref="employee", lazy=True)


# ------------------- Leave Types -------------------

# ------------------- Leaves -------------------
class Leave(db.Model):
    __tablename__ = "leaves"

    id = db.Column(db.Integer, primary_key=True)
    emp_code = db.Column(db.String(50), db.ForeignKey("employees.emp_code"), nullable=False)

    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    # models/models.py

    total_days = db.Column(db.Float)  
# OR (recommended)
# total_days = db.Column(db.Numeric(3,1))
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default="Pending")
    decision_date = db.Column(db.DateTime)

    employee = db.relationship("Employee", backref="leaves", foreign_keys=[emp_code])

class Holiday(db.Model):
    __tablename__ = "holidays" 
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    day = db.Column(db.String(20))
    occasion = db.Column(db.String(100))

class LeaveApprovalConfig(db.Model):
    __tablename__ = "leave_approval_config"

    id = db.Column(db.Integer, primary_key=True)
    level1_approver_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    level2_approver_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    use_manager_l1 = db.Column(db.Boolean, default=False)
class Leavee(db.Model):
    __tablename__ = 'employee_leaves'
    id = db.Column(db.Integer, primary_key=True)
    emp_code = db.Column(db.String(20), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    total_days = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    employee_name = db.Column(db.String(45), nullable=False)
    status = db.Column(db.String(20), default="PENDING_L1")  # PENDING_L1, REJECTED_L1, PENDING_L2, APPROVED
    level1_approver_id = db.Column(db.Integer, nullable=True)
    level2_approver_id = db.Column(db.Integer, nullable=True)
    current_approver_id = db.Column(db.Integer, nullable=True)
    level1_decision_date = db.Column(db.DateTime, nullable=True)
    level2_decision_date = db.Column(db.DateTime, nullable=True)
    leave_type = db.Column(db.String(30), nullable=False)  # Casual Leave, Sick Leave, Leave Without Pay


class EmployeeSalary(db.Model):
    __tablename__ = "employee_salary"
 
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), unique=True)
 
    # Earnings
    basic_percent = db.Column(db.Float, default=50)
    hra_percent = db.Column(db.Float, default=20)
    fixed_allowance = db.Column(db.Float, default=4532)
 
    # Reimbursements
    medical_fixed = db.Column(db.Float, default=1000)
    driver_reimbursement = db.Column(db.Float, default=1000)
 
    # Deductions
    epf_percent = db.Column(db.Float, default=12)
 
    # Salary totals
    gross_salary = db.Column(db.Float, nullable=False)
    total_deductions = db.Column(db.Float, default=0)
    net_salary = db.Column(db.Float, nullable=False)
 
    created_at = db.Column(db.DateTime, server_default=db.func.now())
 
 
# ------------------- Employee Bank Account -----------------
class EmployeeAccount(db.Model):
    __tablename__ = "employee_account"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), unique=True)
    bank_name = db.Column(db.String(100))
    account_number = db.Column(db.String(30))
    ifsc_code = db.Column(db.String(15))
    account_holder_name = db.Column(db.String(100))
class PayrollRun(db.Model):
    __tablename__ = "payroll_run"

    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)

    approved = db.Column(db.Boolean, default=False)
    approved_at = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint('month', 'year', name='uq_payroll_run_month_year'),
    )
class PayrollDetails(db.Model):
    __tablename__ = "payroll_details"
 
    id = db.Column(db.Integer, primary_key=True)
 
    employee_id = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
 
    net_salary = db.Column(db.Float, nullable=False)
    bonus = db.Column(db.Float, default=0)
    deduction = db.Column(db.Float, default=0)
    final_salary = db.Column(db.Float, nullable=False)
    comments = db.Column(db.String(255), nullable=True)  # ✅ NEW FIELD

 
    created_at = db.Column(db.DateTime, server_default=db.func.now())
 
    __table_args__ = (
        db.UniqueConstraint('employee_id', 'month', 'year', name='uq_emp_month_year'),
    )
from models.attendance import Attendance
