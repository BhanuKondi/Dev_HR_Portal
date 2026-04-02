import os
from datetime import timedelta

from flask import Flask, jsonify, redirect, session
from models.db import db
from extensions import mail
from urllib.parse import quote_plus
from sqlalchemy import text
from utils.authz import ROLE_ADMIN, ROLE_USER, get_current_role, get_role_by_name, redirect_for_role


def env_or_config(app: Flask, key: str, default=None):
    return os.getenv(key, app.config.get(key, default))


# ----------------- APP SETUP -----------------
app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile("config.py")

app.config["MAIL_SERVER"] = env_or_config(app, "MAIL_SERVER", "smtp.office365.com")
app.config["MAIL_PORT"] = int(env_or_config(app, "MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = str(env_or_config(app, "MAIL_USE_TLS", "true")).lower() in {"1", "true", "yes"}
app.config["MAIL_USERNAME"] = env_or_config(app, "MAIL_USERNAME", "support@atikes.com")
app.config["MAIL_PASSWORD"] = env_or_config(app, "MAIL_PASSWORD", "*6kF#pP9@vR2n!LqT9")
app.config["MAIL_DEFAULT_SENDER"] = env_or_config(app, "MAIL_DEFAULT_SENDER", app.config["MAIL_USERNAME"] or None)

mail.init_app(app)

password = quote_plus(str(env_or_config(app, "MYSQL_PASSWORD", "")))
mysql_host = env_or_config(app, "MYSQL_HOST", "localhost")
mysql_port = int(env_or_config(app, "MYSQL_PORT", 3306))
mysql_user = env_or_config(app, "MYSQL_USER", "root")
mysql_database = env_or_config(app, "MYSQL_DATABASE", "")
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{mysql_user}:{password}"
    f"@{mysql_host}:{mysql_port}/{mysql_database}"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = env_or_config(app, "SECRET_KEY", "change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = env_or_config(app, "SESSION_COOKIE_SAMESITE", "Lax")
app.config["SESSION_COOKIE_SECURE"] = str(env_or_config(app, "SESSION_COOKIE_SECURE", "false")).lower() in {"1", "true", "yes"}
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SECURE"] = app.config["SESSION_COOKIE_SECURE"]
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
    minutes=int(env_or_config(app, "PERMANENT_SESSION_LIFETIME_MINUTES", 30))
)

# ----------------- DATABASE INIT -----------------
db.init_app(app)





# ----------------- MODELS -----------------
from models.models import User, Role

# ----------------- DEFAULT ADMIN CREATION -----------------
def ensure_core_roles():
    with app.app_context():
        db.create_all()
        existing_roles = {role.name.lower(): role for role in Role.query.all()}
        changed = False

        if ROLE_ADMIN not in existing_roles:
            db.session.add(Role(name="Admin"))
            changed = True

        if ROLE_USER not in existing_roles:
            db.session.add(Role(name="User"))
            changed = True

        if changed:
            db.session.commit()


def ensure_user_profile_photo_column():
    with app.app_context():
        with db.engine.begin() as connection:
            columns = connection.execute(text("SHOW COLUMNS FROM users LIKE 'profile_photo_path'")).fetchall()
            if not columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN profile_photo_path VARCHAR(255) NULL"))


def create_default_admin():
    with app.app_context():
        db.create_all()  # Ensure tables exist

        # Ensure Admin role exists
        admin_role = get_role_by_name("admin")
        if not admin_role:
            admin_role = Role(name="Admin")
            db.session.add(admin_role)
            db.session.commit()

        enable_default_admin = str(env_or_config(app, "ENABLE_DEFAULT_ADMIN", "false")).lower() in {"1", "true", "yes"}
        if not enable_default_admin:
            return

        # Ensure default admin user exists
        admin_email = env_or_config(app, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
        admin_password = env_or_config(app, "DEFAULT_ADMIN_PASSWORD")
        if not admin_password:
            print("Skipping default admin creation because DEFAULT_ADMIN_PASSWORD is not set.")
            return

        admin = User.query.filter_by(email=admin_email).first()
        if not admin:
            admin = User(
                email=admin_email,
                display_name="Administrator",
                role_id=admin_role.id,
                is_active=True,
                must_change_password=True
            )
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            print(f"✔ Default admin created for {admin_email}")

ensure_core_roles()
ensure_user_profile_photo_column()
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
    if "user_id" not in session:
        return redirect("/login")
    return redirect_for_role(get_current_role())

# ----------------- TEST ROUTE -----------------
@app.route("/test")
def test():
    return "Flask app is running!"


@app.route("/health/db")
def health_db():
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return jsonify({
            "status": "ok",
            "database": "reachable"
        }), 200
    except Exception as exc:
        return jsonify({
            "status": "error",
            "database": "unreachable",
            "message": str(exc)
        }), 500

# ----------------- RUN -----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
