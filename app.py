from flask import Flask, redirect, session
from werkzeug.security import generate_password_hash
from models.db import db

# ----------------- APP SETUP -----------------
app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile("config.py")

# SQLAlchemy configuration
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{app.config['MYSQL_USER']}:{app.config['MYSQL_PASSWORD']}"
    f"@{app.config['MYSQL_HOST']}/{app.config['MYSQL_DATABASE']}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = app.config["SECRET_KEY"]

# ----------------- DATABASE INIT -----------------
db.init_app(app)

# ----------------- MODELS -----------------
from models.models import User, Role

# ----------------- DEFAULT ADMIN CREATION -----------------
def create_default_admin():
    with app.app_context():
        db.create_all()  # Ensure tables exist

        # Ensure Admin role exists
        admin_role = Role.query.filter_by(name="Admin").first()
        if not admin_role:
            admin_role = Role(name="Admin")
            db.session.add(admin_role)
            db.session.commit()

        # Ensure default admin user exists
        admin_email = "admin@atikes.com"
        admin = User.query.filter_by(email=admin_email).first()
        if not admin:
            admin = User(
                email=admin_email,
                display_name="Administrator",
                role_id=admin_role.id,
                is_active=True,
                must_change_password=False
            )
            admin.set_password("admin123")  # Default password
            db.session.add(admin)
            db.session.commit()
            print("✔ Default admin created (admin@example.com / admin123)")

create_default_admin()

# ----------------- BLUEPRINT IMPORTS -----------------
# Auth routes
from auth.auth import auth_bp

# Admin routes
from routes.admin.admin_routes import admin_bp
from routes.admin.admin_attendance import admin_attendance_bp
from routes.admin.attendance_routes import attendance_bp

# Employee routes
from routes.employee.employee_routes import employee_bp
from routes.employee.attendance_employee import employee_attendance_bp


# Manager routes
from routes.manager.manager_routes import manager_bp
from routes.manager.attendance_manager import manager_attendance_bp

from routes.manager.manager_team import manager_team_bp  # <-- Add this
from routes.employee.employee_leaves import employee_lbp
from routes.admin.admin_leaves import admin_lbp
from routes.manager.manager_leaves import manager_lbp
# Settings routes
from routes.settings.settings import settings_bp
from routes.api_employees import api_emp
from routes.admin.admin_payroll_routes import admin_payroll_bp
from routes.employee.employee_payroll import employee_payroll_bp
from routes.manager.manager_payroll import manager_payroll_bp
app.register_blueprint(admin_payroll_bp)
# ----------------- BLUEPRINT REGISTRATION -----------------
# Auth
app.register_blueprint(auth_bp)

# Admin
app.register_blueprint(admin_bp)
app.register_blueprint(admin_attendance_bp)
app.register_blueprint(attendance_bp)

# Employee
app.register_blueprint(employee_bp)
app.register_blueprint(employee_attendance_bp)


# Manager
app.register_blueprint(manager_attendance_bp)  # /manager/attendance
      # /manager/leave_management
app.register_blueprint(manager_team_bp)        # /manager/team
app.register_blueprint(manager_bp)             # /manager/dashboard, profile, etc.
app.register_blueprint(manager_payroll_bp)
# Settings
app.register_blueprint(settings_bp)

app.register_blueprint(employee_lbp)
app.register_blueprint(admin_lbp)
app.register_blueprint(manager_lbp)
app.register_blueprint(api_emp)


app.register_blueprint(employee_payroll_bp)


# ----------------- DEFAULT ROUTE -----------------
@app.route("/")
def index():
    user_id = session.get("user_id")
    role_id = session.get("role_id")

    if not user_id:
        return redirect("/login")

    # Fetch role name safely
    try:
        role = Role.query.get(role_id)
        role_name = role.name.lower() if role and role.name else ""
    except Exception:
        role_name = ""

    if role_name == "admin":
        return redirect("/admin/dashboard")
    elif role_name == "manager":
        return redirect("/manager/dashboard")
    else:
        return redirect("/employee/dashboard")

# ----------------- TEST ROUTE -----------------
@app.route("/test")
def test():
    return "Flask app is running!"

# ----------------- RUN -----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)