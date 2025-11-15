
import os
import sqlite3
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
    g,
)

# -------------------------------------------------
# Configuration
# -------------------------------------------------

DATABASE_PATH = os.environ.get("DATABASE_URL", os.path.join(os.path.dirname(__file__), "village_ride.db"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")


# -------------------------------------------------
# Database helpers
# -------------------------------------------------

def get_db():
    if "db" not in g:
        # If DATABASE_URL looks like a URL, fall back to local file
        db_path = DATABASE_PATH
        if db_path.startswith("sqlite:///"):
            db_path = db_path.replace("sqlite:///", "")
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    cur = db.cursor()

    # offered rides
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS rides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver TEXT NOT NULL,
            phone TEXT NOT NULL,
            from_location TEXT NOT NULL,
            to_location TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            seats INTEGER NOT NULL,
            ride_type TEXT NOT NULL,
            from_lat REAL,
            from_lng REAL,
            to_lat REAL,
            to_lng REAL,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_flagged INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cur.execute("CREATE INDEX IF NOT EXISTS idx_rides_date ON rides(date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rides_from_to ON rides(from_location, to_location)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rides_type ON rides(ride_type)")

    # ride requests
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ride_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            passenger TEXT NOT NULL,
            phone TEXT NOT NULL,
            from_location TEXT NOT NULL,
            to_location TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            time_flex TEXT NOT NULL,
            people_count INTEGER NOT NULL,
            note TEXT,
            from_lat REAL,
            from_lng REAL,
            to_lat REAL,
            to_lng REAL,
            status TEXT NOT NULL DEFAULT 'open',
            is_active INTEGER NOT NULL DEFAULT 1,
            is_flagged INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requests_date_status ON ride_requests(date, status)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requests_from_to ON ride_requests(from_location, to_location)"
    )

    # admin users
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
        """
    )

    # config
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    # audit logs
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            ride_id INTEGER,
            request_id INTEGER,
            admin_user TEXT
        )
        """
    )

    # Seed admin user if missing
    cur.execute("SELECT COUNT(*) AS c FROM admin_users")
    row = cur.fetchone()
    if row["c"] == 0:
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD", "admin123")
        # Very simple hash substitute for demo; in production use werkzeug.security
        password_hash = f"plain:{password}"
        cur.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )

    db.commit()


@app.before_request
def ensure_db():
    # initialize db lazily on first request
    init_db()


# -------------------------------------------------
# Helpers
# -------------------------------------------------

RIDE_TYPE_LABELS = {
    "work": "За работа",
    "school": "За училище",
    "healthcare": "За здраве/болница",
    "other": "Друг превоз",
}

TIME_FLEX_LABELS = {
    "flex_30m": "± 30 мин",
    "flex_1h": "± 1 час",
    "morning": "По-скоро сутрин",
    "afternoon": "По-скоро следобед",
}


def parse_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def today_str():
    return date.today().isoformat()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_username"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped


def add_audit(action, ride_id=None, request_id=None):
    db = get_db()
    db.execute(
        "INSERT INTO audit_logs (timestamp, action, ride_id, request_id, admin_user) VALUES (?, ?, ?, ?, ?)",
        (
            datetime.utcnow().isoformat(timespec="seconds"),
            action,
            ride_id,
            request_id,
            session.get("admin_username"),
        ),
    )
    db.commit()


# -------------------------------------------------
# Public routes
# -------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    db = get_db()
    today = today_str()

    # rides for lists + map
    rides_cur = db.execute(
        """
        SELECT * FROM rides
        WHERE is_active = 1
          AND date >= ?
        ORDER BY date ASC, time ASC
        LIMIT 200
        """,
        (today,),
    )
    rides = [dict(r) for r in rides_cur.fetchall()]

    for r in rides:
        r["ride_type_label"] = RIDE_TYPE_LABELS.get(r["ride_type"], "Друг превоз")

    # ride requests for list + map
    req_cur = db.execute(
        """
        SELECT * FROM ride_requests
        WHERE is_active = 1
          AND status = 'open'
          AND date >= ?
        ORDER BY date ASC, time ASC
        LIMIT 200
        """,
        (today,),
    )
    requests = [dict(r) for r in req_cur.fetchall()]

    for req in requests:
        req["time_flex_label"] = TIME_FLEX_LABELS.get(req["time_flex"], "")
        req["status_label"] = req["status"]

    return render_template(
        "index.html",
        rides=rides,
        requests=requests,
        rides_for_map=rides,
        requests_for_map=requests,
    )


@app.route("/offer_ride", methods=["POST"])
def offer_ride():
    db = get_db()
    data = request.get_json(silent=True)
    is_json = data is not None

    if not is_json:
        data = request.form

    driver = (data.get("driver") or "").strip()
    phone = (data.get("phone") or "").strip()
    from_location = (data.get("from_location") or "").strip()
    to_location = (data.get("to_location") or "").strip()
    date_str = (data.get("date") or "").strip()
    time_str = (data.get("time") or "").strip()
    seats = int(data.get("seats") or 1)
    ride_type = (data.get("ride_type") or "other").strip()

    from_lat = data.get("from_lat") or data.get("offer_from_lat")
    from_lng = data.get("from_lng") or data.get("offer_from_lng")
    to_lat = data.get("to_lat") or data.get("offer_to_lat")
    to_lng = data.get("to_lng") or data.get("offer_to_lng")

    errors = {}

    if not driver:
        errors["driver"] = "Моля, въведете име на шофьора."
    if not phone:
        errors["phone"] = "Моля, въведете телефон."
    if not from_location:
        errors["from_location"] = "Моля, въведете място на тръгване."
    if not to_location:
        errors["to_location"] = "Моля, въведете място на пристигане."
    if not date_str:
        errors["date"] = "Моля, изберете дата."
    else:
        try:
            d = parse_date(date_str)
            if d < date.today():
                errors["date"] = "Датата не може да е в миналото."
        except ValueError:
            errors["date"] = "Невалиден формат на дата."
    if not time_str:
        errors["time"] = "Моля, изберете час."

    if seats < 1 or seats > 8:
        errors["seats"] = "Броят места трябва да е между 1 и 8."

    if errors:
        if is_json:
            return jsonify({"error": "Невалидни данни.", "details": errors}), 400
        for msg in errors.values():
            flash(msg, "error")
        return redirect(url_for("index") + "#offer-tab")

    now = datetime.utcnow().isoformat(timespec="seconds")
    db.execute(
        """
        INSERT INTO rides (
            driver, phone, from_location, to_location,
            date, time, seats, ride_type,
            from_lat, from_lng, to_lat, to_lng,
            is_active, is_flagged, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
        """,
        (
            driver,
            phone,
            from_location,
            to_location,
            date_str,
            time_str,
            seats,
            ride_type,
            float(from_lat) if from_lat else None,
            float(from_lng) if from_lng else None,
            float(to_lat) if to_lat else None,
            float(to_lng) if to_lng else None,
            now,
            now,
        ),
    )
    db.commit()

    if is_json:
        return (
            jsonify({"message": "Превозът е предложен успешно."}),
            201,
        )

    flash("Превозът е предложен успешно!", "success")
    return redirect(url_for("index"))


@app.route("/request_ride", methods=["POST"])
def request_ride():
    db = get_db()
    data = request.get_json(silent=True)
    is_json = data is not None

    if not is_json:
        data = request.form

    passenger = (data.get("passenger") or "").strip()
    phone = (data.get("phone") or "").strip()
    from_location = (data.get("from_location") or "").strip()
    to_location = (data.get("to_location") or "").strip()
    date_str = (data.get("date") or "").strip()
    time_str = (data.get("time") or "").strip()
    time_flex = (data.get("time_flex") or "").strip()
    people_count = int(data.get("people_count") or 1)
    note = (data.get("note") or "").strip()

    from_lat = data.get("from_lat") or data.get("request_from_lat")
    from_lng = data.get("from_lng") or data.get("request_from_lng")
    to_lat = data.get("to_lat") or data.get("request_to_lat")
    to_lng = data.get("to_lng") or data.get("request_to_lng")

    errors = {}

    if not passenger:
        errors["passenger"] = "Моля, въведете име на пътника."
    if not phone:
        errors["phone"] = "Моля, въведете телефон."
    if not from_location:
        errors["from_location"] = "Моля, въведете място на тръгване."
    if not to_location:
        errors["to_location"] = "Моля, въведете място на пристигане."
    if not date_str:
        errors["date"] = "Моля, изберете дата."
    else:
        try:
            d = parse_date(date_str)
            if d < date.today():
                errors["date"] = "Датата не може да е в миналото."
        except ValueError:
            errors["date"] = "Невалиден формат на дата."
    if not time_str:
        errors["time"] = "Моля, изберете час."
    if time_flex not in TIME_FLEX_LABELS:
        errors["time_flex"] = "Моля, изберете валидна гъвкавост на времето."
    if people_count < 1 or people_count > 4:
        errors["people_count"] = "Броят хора трябва да е между 1 и 4."

    if errors:
        if is_json:
            return jsonify({"error": "Невалидни данни.", "details": errors}), 400
        for msg in errors.values():
            flash(msg, "error")
        return redirect(url_for("index") + "#requests-tab")

    now = datetime.utcnow().isoformat(timespec="seconds")
    cur = db.execute(
        """
        INSERT INTO ride_requests (
            passenger, phone, from_location, to_location,
            date, time, time_flex, people_count, note,
            from_lat, from_lng, to_lat, to_lng,
            status, is_active, is_flagged, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 1, 0, ?, ?)
        """,
        (
            passenger,
            phone,
            from_location,
            to_location,
            date_str,
            time_str,
            time_flex,
            people_count,
            note or None,
            float(from_lat) if from_lat else None,
            float(from_lng) if from_lng else None,
            float(to_lat) if to_lat else None,
            float(to_lng) if to_lng else None,
            now,
            now,
        ),
    )
    db.commit()
    request_id = cur.lastrowid

    if is_json:
        return (
            jsonify(
                {
                    "message": "Заявката за превоз е публикувана успешно.",
                    "id": request_id,
                }
            ),
            201,
        )

    flash("Заявката за превоз е публикувана успешно.", "success")
    return redirect(url_for("index") + "#requests-tab")


@app.route("/search_rides", methods=["GET"])
def search_rides():
    db = get_db()
    q_from = (request.args.get("from") or "").strip()
    q_to = (request.args.get("to") or "").strip()
    q_date = (request.args.get("date") or "").strip()
    q_type = (request.args.get("type") or "").strip()

    today = today_str()
    params = []
    where_clauses = ["is_active = 1", "date >= ?"]
    params.append(today)

    if q_from:
        where_clauses.append("LOWER(from_location) LIKE LOWER(?)")
        params.append(f"%{q_from}%")
    if q_to:
        where_clauses.append("LOWER(to_location) LIKE LOWER(?)")
        params.append(f"%{q_to}%")
    if q_date:
        where_clauses.append("date = ?")
        params.append(q_date)
    if q_type:
        where_clauses.append("ride_type = ?")
        params.append(q_type)

    sql = f"""
        SELECT * FROM rides
        WHERE {' AND '.join(where_clauses)}
        ORDER BY date ASC, time ASC
        LIMIT 200
    """

    cur = db.execute(sql, params)
    rides = [dict(r) for r in cur.fetchall()]
    for r in rides:
        r["ride_type_label"] = RIDE_TYPE_LABELS.get(r["ride_type"], "Друг превоз")

    return jsonify(rides)


@app.route("/search_requests", methods=["GET"])
def search_requests():
    db = get_db()
    q_from = (request.args.get("from") or "").strip()
    q_to = (request.args.get("to") or "").strip()
    q_date = (request.args.get("date") or "").strip()
    q_status = (request.args.get("status") or "open").strip() or "open"

    today = today_str()
    params = []
    where_clauses = ["is_active = 1", "date >= ?"]
    params.append(today)

    if q_status:
        where_clauses.append("status = ?")
        params.append(q_status)
    if q_from:
        where_clauses.append("LOWER(from_location) LIKE LOWER(?)")
        params.append(f"%{q_from}%")
    if q_to:
        where_clauses.append("LOWER(to_location) LIKE LOWER(?)")
        params.append(f"%{q_to}%")
    if q_date:
        where_clauses.append("date = ?")
        params.append(q_date)

    sql = f"""
        SELECT * FROM ride_requests
        WHERE {' AND '.join(where_clauses)}
        ORDER BY date ASC, time ASC
        LIMIT 200
    """

    cur = db.execute(sql, params)
    requests = [dict(r) for r in cur.fetchall()]
    for req in requests:
        req["time_flex_label"] = TIME_FLEX_LABELS.get(req["time_flex"], "")
        req["status_label"] = req["status"]

    return jsonify(requests)


# -------------------------------------------------
# Admin routes (simplified)
# -------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()

        db = get_db()
        cur = db.execute(
            "SELECT * FROM admin_users WHERE username = ?", (username,)
        )
        user = cur.fetchone()
        error = None

        if user is None:
            error = "Невалидни данни за вход."
        else:
            stored = user["password_hash"]
            if not stored.startswith("plain:") or stored != f"plain:{password}":
                error = "Невалидни данни за вход."

        if error:
            flash(error, "error")
        else:
            session["admin_username"] = username
            flash("Успешен вход в админ панела.", "success")
            return redirect(url_for("admin_dashboard"))

    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Излязохте от админ панела.", "success")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    today = today_str()

    total_rides = db.execute("SELECT COUNT(*) FROM rides").fetchone()[0]
    rides_today = db.execute(
        "SELECT COUNT(*) FROM rides WHERE date = ?", (today,)
    ).fetchone()[0]
    upcoming_rides = db.execute(
        "SELECT COUNT(*) FROM rides WHERE date > ?", (today,)
    ).fetchone()[0]

    active_requests = db.execute(
        "SELECT COUNT(*) FROM ride_requests WHERE status = 'open' AND is_active = 1 AND date >= ?",
        (today,),
    ).fetchone()[0]
    requests_today = db.execute(
        "SELECT COUNT(*) FROM ride_requests WHERE date = ?", (today,)
    ).fetchone()[0]

    return render_template(
        "admin/dashboard.html",
        total_rides=total_rides,
        rides_today=rides_today,
        upcoming_rides=upcoming_rides,
        active_requests=active_requests,
        requests_today=requests_today,
    )


@app.route("/admin/rides")
@admin_required
def admin_rides():
    db = get_db()
    cur = db.execute(
        "SELECT * FROM rides ORDER BY date DESC, time DESC LIMIT 500"
    )
    rides = [dict(r) for r in cur.fetchall()]
    for r in rides:
        r["ride_type_label"] = RIDE_TYPE_LABELS.get(r["ride_type"], "Друг превоз")
    return render_template("admin/rides_list.html", rides=rides)


@app.route("/admin/requests")
@admin_required
def admin_requests():
    db = get_db()
    cur = db.execute(
        "SELECT * FROM ride_requests ORDER BY date DESC, time DESC LIMIT 500"
    )
    requests = [dict(r) for r in cur.fetchall()]
    for req in requests:
        req["time_flex_label"] = TIME_FLEX_LABELS.get(req["time_flex"], "")
    return render_template("admin/requests_list.html", requests=requests)


@app.route("/admin/logs")
@admin_required
def admin_logs():
    db = get_db()
    cur = db.execute(
        "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 500"
    )
    logs = [dict(r) for r in cur.fetchall()]
    return render_template("admin/logs.html", logs=logs)


# -------------------------------------------------
# Entry point
# -------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
