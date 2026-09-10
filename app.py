from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
import secrets
import time

app = Flask(__name__)
app.config["SECRET_KEY"] = "chat-ruletka-secret-change-this"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

ADMIN_PASSWORD = "Nurlibek19771983"
DB = "chat_ruletka.db"

# Waiting users: socket_id -> True
waiting = set()

# socket_id -> room_id
user_rooms = {}

# room_id -> [socket_id, socket_id]
rooms = {}


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visitor_id TEXT UNIQUE,
            first_seen INTEGER,
            last_seen INTEGER
        )
    """)
    conn.commit()
    conn.close()


def touch_user(visitor_id):
    now = int(time.time())
    conn = db()
    conn.execute("""
        INSERT INTO users(visitor_id, first_seen, last_seen)
        VALUES (?, ?, ?)
        ON CONFLICT(visitor_id)
        DO UPDATE SET last_seen=excluded.last_seen
    """, (visitor_id, now, now))
    conn.commit()
    conn.close()


def online_count():
    # "Online" here means currently connected to the website.
    return len(user_rooms) + len(waiting)


def find_partner(my_sid):
    for sid in list(waiting):
        if sid != my_sid:
            waiting.discard(sid)
            return sid
    return None


def make_room(a, b):
    room_id = secrets.token_urlsafe(12)
    rooms[room_id] = [a, b]
    user_rooms[a] = room_id
    user_rooms[b] = room_id
    join_room(room_id, sid=a)
    join_room(room_id, sid=b)
    return room_id


@app.route("/")
def index():
    if "visitor_id" not in session:
        session["visitor_id"] = secrets.token_urlsafe(16)
    touch_user(session["visitor_id"])
    return render_template("index.html")


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin"))
        return render_template("admin.html", error="Parol qáte.")

    if not session.get("is_admin"):
        return render_template("admin.html", login=True)

    conn = db()
    total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()

    return render_template(
        "admin.html",
        login=False,
        online=online_count(),
        total=total
    )


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin"))


@socketio.on("connect")
def connected():
    visitor_id = session.get("visitor_id")
    if not visitor_id:
        visitor_id = secrets.token_urlsafe(16)
        session["visitor_id"] = visitor_id

    touch_user(visitor_id)
    emit("connected_ok", {"message": "Baylanıs ornatıldı."})


@socketio.on("find")
def find():
    sid = request.sid

    if sid in user_rooms:
        emit("system", {"text": "Siz házir suhbatlasıp atırsız."})
        return

    waiting.discard(sid)
    partner = find_partner(sid)

    if partner is None:
        waiting.add(sid)
        emit("searching")
        return

    room_id = make_room(sid, partner)

    emit("matched", {"room": room_id}, to=sid)
    emit("matched", {"room": room_id}, to=partner)


@socketio.on("message")
def message(data):
    sid = request.sid
    room_id = user_rooms.get(sid)

    if not room_id:
        emit("system", {"text": "Aldın «Baslaw» túymesin basıń."})
        return

    text = str(data.get("text", "")).strip()
    if not text:
        return

    # Basic length limit
    text = text[:1000]

    emit("message", {"text": text}, to=room_id, include_self=True)


@socketio.on("next")
def next_user():
    sid = request.sid
    stop_current(sid, tell_partner=True)
    find()


@socketio.on("stop")
def stop():
    sid = request.sid
    waiting.discard(sid)
    stop_current(sid, tell_partner=True)
    emit("stopped")


def stop_current(sid, tell_partner=True):
    room_id = user_rooms.pop(sid, None)

    if not room_id:
        return

    members = rooms.pop(room_id, [])
    partner = next((x for x in members if x != sid), None)

    try:
        leave_room(room_id, sid=sid)
    except Exception:
        pass

    if partner:
        user_rooms.pop(partner, None)
        try:
            leave_room(room_id, sid=partner)
        except Exception:
            pass

        if tell_partner:
            emit(
                "partner_left",
                {"text": "Suhbatlasıwshı suhbatı toqtattı."},
                to=partner
            )


@socketio.on("disconnect")
def disconnected():
    sid = request.sid
    waiting.discard(sid)
    stop_current(sid, tell_partner=True)


init_db()

if __name__ == "__main__":
    print("================================")
    print(" QARAQALPAQ CHAT RULETKA")
    print(" Server iske túspekte...")
    print(" http://127.0.0.1:5000")
    print("================================")
    socketio.run(app, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)
