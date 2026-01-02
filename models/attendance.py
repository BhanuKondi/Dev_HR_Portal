'''from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from models.db import db

# Load IST timezone; fallback to UTC
try:
    IST = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    IST = ZoneInfo("UTC")


SHIFT_START_HOUR = 10  # 10 AM
SHIFT_END_HOUR = 6     # 6 AM next day

class Attendance(db.Model):
    __tablename__ = "attendance"
  
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    transaction_no = db.Column(db.Integer, nullable=False)

    clock_in = db.Column(db.DateTime(timezone=True), nullable=False)
    clock_out = db.Column(db.DateTime(timezone=True), nullable=True)

    duration_seconds = db.Column(db.Integer, nullable=True)

    date = db.Column(db.Date, nullable=False)

    # New fields for shift boundaries
    shift_start = db.Column(db.DateTime(timezone=True), nullable=False)
    shift_end = db.Column(db.DateTime(timezone=True), nullable=False)

    def finish(self, out_time):
        """
        Complete the attendance by setting clock_out and computing duration.
        """
        self.clock_out = out_time

        if self.clock_in and self.clock_out:
            delta = (self.clock_out - self.clock_in).total_seconds()
            self.duration_seconds = int(delta) if delta > 0 else 0
        else:
            self.duration_seconds = 0

    @staticmethod
    def get_shift_datetime(now: datetime):
        """
        Return shift_start and shift_end datetime for the given timestamp.
        Handles 10 AM → 6 AM next day shift.
        """
        shift_start_dt = now.replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
        if now.hour < SHIFT_END_HOUR:  # Early morning → belongs to previous day's shift
            shift_start_dt -= timedelta(days=1)
        shift_end_dt = shift_start_dt + timedelta(hours=20)  # 10 AM → 6 AM next day
        return shift_start_dt, shift_end_dt

    @staticmethod
    def get_shift_date(now: datetime):
        """
        Return the date that represents the shift for this timestamp.
        """
        if now.hour < SHIFT_END_HOUR:
            return (now - timedelta(days=1)).date()
        return now.date()
'''
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from models.db import db
 
# ===================== TIMEZONE =====================
try:
    IST = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    IST = ZoneInfo("UTC")
 
# ===================== SHIFT CONFIG =====================
SHIFT_START_HOUR = 7     # 7 AM
SHIFT_END_HOUR = 7       # 7 AM next day
MAX_SHIFT_SECONDS = 24 * 60 * 60  # 24 hours cap
 
# ===================== MODEL =====================
class Attendance(db.Model):
    __tablename__ = "attendance"
 
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    transaction_no = db.Column(db.Integer, nullable=False)
 
    clock_in = db.Column(db.DateTime(timezone=True), nullable=False)
    clock_out = db.Column(db.DateTime(timezone=True), nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)
 
    # Shift date (business date)
    date = db.Column(db.Date, nullable=False)
 
    # Shift boundaries
    shift_start = db.Column(db.DateTime(timezone=True), nullable=False)
    shift_end = db.Column(db.DateTime(timezone=True), nullable=False)
 
    # ===================== METHODS =====================
    def finish(self, out_time: datetime):
        """
        Complete attendance safely (manual or auto clock-out).
        Caps duration at 24 hours.
        """
        self.clock_out = out_time
 
        if self.clock_in and self.clock_out:
            ci = self.clock_in
            co = self.clock_out
 
            # Make naive datetimes timezone-aware
            if ci.tzinfo is None:
                ci = ci.replace(tzinfo=IST)
            if co.tzinfo is None:
                co = co.replace(tzinfo=IST)
 
            seconds = int((co - ci).total_seconds())
            self.duration_seconds = min(max(seconds, 0), MAX_SHIFT_SECONDS)
        else:
            self.duration_seconds = 0
 
    # ===================== STATIC HELPERS =====================
    @staticmethod
    def get_shift_datetime(now: datetime):
        """
        Returns shift_start and shift_end for 7 AM → 7 AM shift.
        """
        shift_start = now.replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
 
        # Early morning belongs to previous day's shift
        if now.hour < SHIFT_START_HOUR:
            shift_start -= timedelta(days=1)
 
        shift_end = shift_start + timedelta(hours=24)
 
        return shift_start, shift_end
 
    @staticmethod
    def get_shift_date(now: datetime):
        """
        Business date for the shift (7 AM cutoff).
        """
        if now.hour < SHIFT_END_HOUR:
            return (now - timedelta(days=1)).date()
        return now.date()