import os
import re
import json
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, flash, redirect, render_template, request, session, url_for, abort
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, static_folder='static')

app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "app.sqlite3")
    print("WARNING: Using SQLite database - data will not persist on server restart!")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["SESSION_COOKIE_SECURE"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)

db = SQLAlchemy(app)

UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
DB_READY = False

ADMIN_EMAIL = "admin@sece.ac.in"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@1234")

STUDENT_CREDENTIALS = {
    "ragul.s2025@sece.ac.in": ("Ragul S", "Ragul@2025"),
    "santhoshkumarr.r.v2025@sece.ac.in": ("Santhoshkumar R V", "Santhosh@2025"),
    "praganesh.s2025@sece.ac.in": ("Praganesh S", "Praganesh@2025"),
    "rahul.b2025@sece.ac.in": ("Rahul B", "Rahul@2025"),
    "saikarthik.g.j2025@sece.ac.in": ("Saikarthik G J", "Saikarthik@2025"),
    "praveen.r2025@sece.ac.in": ("Praveen R", "Praveenr@2025"),
    "praveen.j2025@sece.ac.in": ("Praveen J", "Praveenj@2025"),
    "ranjithbala.b2025@sece.ac.in": ("Ranjithbala B", "Ranjith@2025"),
    "pradeep.r.k2025@sece.ac.in": ("Pradeep R K", "Pradeep@2025"),
    "rajapandi.d2025@sece.ac.in": ("Rajapandi D", "Rajapandi@2025"),
}

VALID_CATEGORIES = {"Electrical", "Plumbing and Water", "Wifi", "Cleaning", "Furniture", "Others"}
VALID_PRIORITIES = {"Low", "Medium", "High"}
VALID_STATUSES = {"Pending", "In Progress", "Resolved"}
VALID_HOSTEL_TYPES = {"boys", "girls"}
VALID_BLOCKS = {"A", "B", "C", "D", "E", "F"}


def sanitize_string(text, max_length=255):
    if not text:
        return ""
    text = str(text).strip()
    text = re.sub(r'[<>\"\'%;()&+]', '', text)
    return text[:max_length]


def sanitize_description(text, max_length=500):
    if not text:
        return ""
    text = str(text).strip()
    text = re.sub(r'<[^>]+>', '', text)
    return text[:max_length]


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            flash("Please login first.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("role") == "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


class Complaint(db.Model):
    __tablename__ = "complaints"
    id = db.Column(db.Integer, primary_key=True)
    student_email = db.Column(db.String(120), nullable=False, index=True)
    student_name = db.Column(db.String(120), nullable=False)
    room_number = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    priority = db.Column(db.String(10), nullable=False)
    description = db.Column(db.Text, nullable=False)
    hostel_type = db.Column(db.String(10), nullable=True)
    block = db.Column(db.String(5), nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    admin_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "student_email": self.student_email,
            "student_name": self.student_name,
            "room_number": self.room_number,
            "category": self.category,
            "priority": self.priority,
            "description": self.description,
            "hostel_type": self.hostel_type,
            "block": self.block,
            "image_filename": self.image_filename,
            "status": self.status,
            "admin_note": self.admin_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class IssueCounter(db.Model):
    __tablename__ = "issue_counter"
    id = db.Column(db.Integer, primary_key=True)
    total = db.Column(db.Integer, nullable=False, default=0)

    @classmethod
    def get(cls):
        row = cls.query.first()
        if not row:
            row = cls(total=0)
            db.session.add(row)
            db.session.commit()
        return row


def _allowed_image(filename):
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in {"png", "jpg", "jpeg", "webp", "gif"}


def _init_db():
    global DB_READY
    if not DB_READY:
        db_type = "PostgreSQL" if os.environ.get("DATABASE_URL") else "SQLite"
        print(f"[HOSTEL APP] Initializing with {db_type} database...")
        db.create_all()
        counter = IssueCounter.get()
        if counter.total == 0:
            existing = Complaint.query.count()
            if existing:
                counter.total = existing
                db.session.commit()
        print(f"[HOSTEL APP] Database ready. Total complaints: {IssueCounter.get().total}")
        DB_READY = True


@app.before_request
def _setup():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    _init_db()


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.route("/")
def login():
    if "user" in session:
        return redirect(url_for("welcome"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def handle_login():
    email = (request.form.get("email") or "").strip().lower()
    password = (request.form.get("password") or "").strip()

    if not email or not password:
        return render_template("login.html", error="Please enter email and password.")

    email = sanitize_string(email, 120)
    
    if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        return render_template("login.html", error="Invalid email format.")

    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        session.permanent = True
        session["user"] = email
        session["role"] = "admin"
        session["full_name"] = "Administrator"
        session["login_time"] = datetime.utcnow().isoformat()
        return redirect(url_for("welcome"))

    if email in STUDENT_CREDENTIALS:
        display_name, correct_pw = STUDENT_CREDENTIALS[email]
        if password == correct_pw:
            session.permanent = True
            session["user"] = email
            session["role"] = "student"
            session["full_name"] = display_name
            session["login_time"] = datetime.utcnow().isoformat()
            return redirect(url_for("welcome"))
        return render_template("login.html", error="Incorrect password. Please try again.")

    return render_template("login.html", error="Email not registered. Use your official SECE 2025 email.")


@app.route("/welcome")
@login_required
def welcome():
    cumulative_total = IssueCounter.get().total

    if session.get("role") == "admin":
        complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()

        from sqlalchemy import func
        cat_rows = db.session.query(Complaint.category, func.count(Complaint.id)).group_by(Complaint.category).all()
        cat_labels = [r[0] for r in cat_rows]
        cat_counts = [r[1] for r in cat_rows]

        pri_rows = db.session.query(Complaint.priority, func.count(Complaint.id)).group_by(Complaint.priority).all()
        pri_dict = {r[0]: r[1] for r in pri_rows}

        now = datetime.utcnow()
        month_labels, monthly_issued, monthly_resolved = [], [], []
        for i in range(5, -1, -1):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            month_labels.append(datetime(y, m, 1).strftime("%b %Y"))
            issued = sum(1 for c in complaints if c.created_at.month == m and c.created_at.year == y)
            resolved = sum(1 for c in complaints if c.status == "Resolved" and c.updated_at.month == m and c.updated_at.year == y)
            monthly_issued.append(issued)
            monthly_resolved.append(resolved)
    else:
        complaints = Complaint.query.filter_by(student_email=session["user"]).order_by(Complaint.created_at.desc()).all()
        cat_labels = cat_counts = month_labels = monthly_issued = monthly_resolved = []
        pri_dict = {}

    active = len(complaints)
    pending = sum(1 for c in complaints if c.status == "Pending")
    in_progress = sum(1 for c in complaints if c.status == "In Progress")
    resolved = sum(1 for c in complaints if c.status == "Resolved")

    stats = dict(total=cumulative_total, active=active, pending=pending, in_progress=in_progress, resolved=resolved)

    return render_template(
        "welcome.html", email=session["user"], full_name=session.get("full_name", ""),
        role=session.get("role"), complaints=complaints, stats=stats,
        cat_labels=json.dumps(cat_labels), cat_counts=json.dumps(cat_counts),
        pri_dict=json.dumps(pri_dict), month_labels=json.dumps(month_labels),
        monthly_issued=json.dumps(monthly_issued), monthly_resolved=json.dumps(monthly_resolved),
    )


@app.route("/complaint")
@login_required
def complaint():
    if session.get("role") == "admin":
        flash("Admins cannot submit complaints.")
        return redirect(url_for("welcome"))
    return render_template("complaint.html", full_name=session.get("full_name", ""))


@app.route("/submit_complaint", methods=["POST"])
@login_required
def submit_complaint():
    if session.get("role") == "admin":
        return redirect(url_for("welcome"))

    student_name = sanitize_string(request.form.get("name", ""), 120)
    room_number = sanitize_string(request.form.get("room", ""), 50)
    hostel_type_raw = (request.form.get("hostel_type") or "").strip().lower()
    block_raw = (request.form.get("block") or "").strip().upper()
    category_raw = (request.form.get("category") or "").strip()
    priority_raw = (request.form.get("priority") or "").strip()
    description = sanitize_description(request.form.get("description", ""), 500)

    hostel_type = hostel_type_raw if hostel_type_raw in VALID_HOSTEL_TYPES else None
    block = block_raw if block_raw in VALID_BLOCKS else None
    category = category_raw if category_raw in VALID_CATEGORIES else None
    priority = priority_raw if priority_raw in VALID_PRIORITIES else "Medium"

    errors = []
    if not student_name:
        errors.append("Student name is required.")
    if not room_number:
        errors.append("Room number is required.")
    if not category:
        errors.append("Please select a valid category.")
    if not description:
        errors.append("Description is required.")

    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("complaint"))

    c = Complaint(
        student_email=session["user"], student_name=student_name, room_number=room_number,
        hostel_type=hostel_type, block=block, category=category, priority=priority,
        description=description, status="Pending",
    )
    db.session.add(c)
    db.session.flush()

    counter = IssueCounter.get()
    counter.total += 1
    db.session.commit()

    uploaded = request.files.get("image")
    if uploaded and uploaded.filename and uploaded.filename.strip():
        if _allowed_image(uploaded.filename):
            ext = uploaded.filename.rsplit(".", 1)[1].lower()
            final_filename = f"{c.id}_{secrets.token_hex(8)}.{ext}"
            uploaded.save(os.path.join(UPLOAD_DIR, final_filename))
            c.image_filename = final_filename
            db.session.commit()
        else:
            flash("Invalid image type. PNG, JPG, JPEG, WEBP allowed.", "warning")

    flash("Complaint submitted successfully!", "success")
    return redirect(url_for("welcome"))


@app.route("/admin/update_complaint/<int:cid>", methods=["POST"])
@login_required
@admin_required
def update_complaint(cid):
    c = Complaint.query.get_or_404(cid)
    new_status = (request.form.get("status") or "").strip()
    admin_note = sanitize_description(request.form.get("admin_note", ""), 500)

    if new_status in VALID_STATUSES:
        c.status = new_status
    c.admin_note = admin_note
    c.updated_at = datetime.utcnow()
    db.session.commit()
    flash(f"Complaint #{cid} updated to '{c.status}'.", "success")
    return redirect(url_for("welcome"))


@app.route("/admin/delete_complaint/<int:cid>", methods=["POST"])
@login_required
@admin_required
def delete_complaint(cid):
    c = Complaint.query.get_or_404(cid)
    if c.image_filename:
        img_path = os.path.join(UPLOAD_DIR, c.image_filename)
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except OSError:
                pass
    db.session.delete(c)
    db.session.commit()
    flash(f"Complaint #{cid} deleted.", "success")
    return redirect(url_for("welcome"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.errorhandler(403)
def forbidden(e):
    return render_template("login.html", error="Access denied."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("login.html", error="Page not found."), 404


@app.errorhandler(500)
def server_error(e):
    db.session.rollback()
    return render_template("login.html", error="Server error. Please try again."), 500


if __name__ == "__main__":
    app.run(debug=False, port=int(os.environ.get("PORT", 5000)))
