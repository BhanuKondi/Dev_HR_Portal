from flask import Blueprint, jsonify, session
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from models.db import db
from models.attendance import Attendance, IST, SHIFT_START_HOUR, SHIFT_END_HOUR, MAX_SHIFT_SECONDS
 
attendance_bp = Blueprint("attendance_bp", __name__, url_prefix="/attendance")
 
# ===================== HELPERS =====================
def get_shift_date(now):
    """Shift date logic for 7 AM → 7 AM"""
    if now.hour < SHIFT_END_HOUR:
        return (now - timedelta(days=1)).date()
    return now.date()
 
 
def auto_clock_out_after_7am(user_id=None):
    """
    Auto clock-out ONLY if user forgot to clock out
    and shift end (7 AM) has passed.
    """
    now = datetime.now(IST)
 
    query = Attendance.query.filter_by(clock_out=None)
    if user_id:
        query = query.filter_by(user_id=user_id)
 
    open_records = query.all()
 
    for record in open_records:
        shift_end = record.shift_end
        if shift_end.tzinfo is None:
            shift_end = shift_end.replace(tzinfo=IST)
 
        if now >= shift_end:
            clock_in = record.clock_in
            if clock_in.tzinfo is None:
                clock_in = clock_in.replace(tzinfo=IST)
 
            duration = int((shift_end - clock_in).total_seconds())
            duration = min(duration, MAX_SHIFT_SECONDS)
 
            record.clock_out = shift_end
            record.duration_seconds = duration
 
    db.session.commit()
 
# ===================== ROUTES =====================
@attendance_bp.route("/clock_in", methods=["POST"])
def clock_in():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Login required"}), 401
 
    # Auto close old sessions if shift ended
    auto_clock_out_after_7am(user_id)
 
    # 🔴 CHECK FOR EXISTING OPEN SESSION
    open_record = Attendance.query.filter_by(
        user_id=user_id,
        clock_out=None
    ).first()
 
    if open_record:
        return jsonify({
            "error": "You are already clocked in. Please clock out first."
        }), 400
 
    now = datetime.now(IST)
    shift_day = get_shift_date(now)
 
    shift_start = now.replace(
        hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0
    )
    if now.hour < SHIFT_START_HOUR:
        shift_start -= timedelta(days=1)
 
    shift_end = shift_start + timedelta(hours=24)
 
    last_txn = Attendance.query.filter_by(
        user_id=user_id,
        date=shift_day
    ).order_by(
        Attendance.transaction_no.desc()
    ).first()
 
    next_txn = last_txn.transaction_no + 1 if last_txn else 1
 
    attendance = Attendance(
        user_id=user_id,
        transaction_no=next_txn,
        clock_in=now,
        date=shift_day,
        shift_start=shift_start,
        shift_end=shift_end
    )
 
    db.session.add(attendance)
    db.session.commit()
 
    return jsonify({
        "message": "Clocked In",
        "transaction_no": next_txn
    })
 
@attendance_bp.route("/clock_out", methods=["POST"])
def clock_out():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Login required"}), 401
 
    open_record = Attendance.query.filter_by(user_id=user_id, clock_out=None).first()
    if not open_record:
        return jsonify({"error": "No active session"}), 400
 
    now = datetime.now(IST)
    clock_in = open_record.clock_in
    if clock_in.tzinfo is None:
        clock_in = clock_in.replace(tzinfo=IST)
 
    duration = int((now - clock_in).total_seconds())
    duration = min(duration, MAX_SHIFT_SECONDS)
 
    open_record.clock_out = now
    open_record.duration_seconds = duration
 
    db.session.commit()
 
    return jsonify({
        "message": "Clocked Out",
        "duration_seconds": duration,
        "transaction_no": open_record.transaction_no
    })
 
 
@attendance_bp.route("/status", methods=["GET"])
def status():
    user_id = session.get("user_id")
    auto_clock_out_after_7am(user_id)
    open_record = Attendance.query.filter_by(user_id=user_id, clock_out=None).first()
    return jsonify({"active": bool(open_record)})
 
 
@attendance_bp.route("/current", methods=["GET"])
def current_session():
    user_id = session.get("user_id")
    auto_clock_out_after_7am(user_id)
    record = Attendance.query.filter_by(user_id=user_id, clock_out=None).first()
    if not record:
        return jsonify({"active": False})
    return jsonify({
        "active": True,
        "clock_in": record.clock_in.isoformat(),
        "shift_start": record.shift_start.isoformat(),
        "shift_end": record.shift_end.isoformat()
    })
 
@attendance_bp.route("/today-summary", methods=["GET"])
def today_summary():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Login required"}), 401
 
    # Auto clock-out forgotten sessions
    auto_clock_out_after_7am(user_id)
 
    now = datetime.now(IST)
    shift_day = get_shift_date(now)
 
    # Fetch all today's attendance records for the user
    records = Attendance.query.filter_by(user_id=user_id, date=shift_day).order_by(
        Attendance.transaction_no
    ).all()
 
    total_seconds = 0
    transactions = []
 
    for r in records:
        # Recalculate duration_seconds if missing
        if r.clock_in and r.clock_out:
            clock_in = r.clock_in
            clock_out = r.clock_out
 
            if clock_in.tzinfo is None:
                clock_in = clock_in.replace(tzinfo=IST)
            if clock_out.tzinfo is None:
                clock_out = clock_out.replace(tzinfo=IST)
 
            r.duration_seconds = min(int((clock_out - clock_in).total_seconds()), MAX_SHIFT_SECONDS)
        else:
            r.duration_seconds = 0
 
        # Sum total duration
        total_seconds += r.duration_seconds
 
        # Prepare transaction for display
        transactions.append({
            "transaction_no": r.transaction_no,
            "clock_in": r.clock_in.strftime("%d/%m/%Y %I:%M %p") if r.clock_in else "-",
            "clock_out": r.clock_out.strftime("%d/%m/%Y %I:%M %p") if r.clock_out else "-",
            "duration_seconds": r.duration_seconds,
            "shift_start": r.shift_start.strftime("%d/%m/%Y %I:%M %p") if r.shift_start else "-",
            "shift_end": r.shift_end.strftime("%d/%m/%Y %I:%M %p") if r.shift_end else "-"
        })
 
    # Commit any updated durations to DB
    db.session.commit()
 
    # Convert total_seconds to HH:MM:SS
    hrs = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    secs = total_seconds % 60
 
    return jsonify({
        "worked": f"{hrs:02}:{mins:02}:{secs:02}",
        "total_seconds": total_seconds,
        "transactions": transactions
    })
 
 