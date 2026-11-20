import os
import sqlite3
import uuid
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
DB_PATH = os.path.join(BASE_DIR, "easystay.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "upload")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            location TEXT NOT NULL,
            rent INTEGER NOT NULL,
            amenities TEXT NOT NULL,
            video_url TEXT DEFAULT '',
            owner TEXT NOT NULL,
            owner_key TEXT NOT NULL,
            saved_by_owner INTEGER DEFAULT 0
        )
    """)

    cur.execute("SELECT COUNT(*) AS cnt FROM rooms")
    if cur.fetchone()["cnt"] == 0:
        sample_rooms = [
            ("Sharma PG & Boys Hostel", "Student", "Near Engineering College Gate 2", 4500, "Wi-Fi, 24x7 Water, Bed & Table", "", "Rakesh Sharma - 9876543210", "owner1", 1),
            ("GreenView 1RK Flat", "Employee", "IT Park Road, Sector 4", 8500, "Attached Washroom, Bike Parking", "", "Amit Verma - 9811223344", "owner2", 0),
            ("Kisan & Worker Niwas", "Worker", "Industrial Area Phase 1", 2200, "Shared Room, 24x7 Water", "", "Suresh Yadav - 9899887766", "owner3", 0),
            ("Sunrise Girls PG", "Student", "Station Road, Near Main Market", 5000, "Wi-Fi, CCTV Security", "", "Sunita Devi - 9822334455", "owner4", 0),
        ]
        cur.executemany("""
            INSERT INTO rooms (title, category, location, rent, amenities, video_url, owner, owner_key, saved_by_owner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_rooms)

    conn.commit()
    conn.close()


def serialize_room(row):
    amenities_list = [x.strip() for x in (row["amenities"] or "").split(",") if x.strip()]
    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "location": row["location"],
        "rent": row["rent"],
        "amenities": amenities_list,
        "videoUrl": row["video_url"],
        "owner": row["owner"],
        "savedByOwner": bool(row["saved_by_owner"])
    }


@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/upload/<filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/api/rooms", methods=["GET"])
def get_rooms():
    location_q = request.args.get("location", "").strip().lower()
    max_rent = request.args.get("max_rent", "999999")
    try:
        max_rent_val = int(max_rent)
    except ValueError:
        max_rent_val = 999999

    conn = get_db()
    rows = conn.execute("SELECT * FROM rooms ORDER BY id DESC").fetchall()
    conn.close()

    result = []
    for r in rows:
        item = serialize_room(r)
        if location_q and location_q not in item["location"].lower():
            continue
        if item["rent"] > max_rent_val:
            continue
        result.append(item)
    return jsonify(result)


@app.route("/api/rooms", methods=["POST"])
def create_room():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "Student").strip()
    location = request.form.get("location", "").strip()
    owner = request.form.get("owner", "").strip()
    amenities = request.form.get("amenities", "Basic Room").strip()
    owner_key = request.form.get("owner_key", "").strip()
    try:
        rent = int(request.form.get("rent", "0"))
    except ValueError:
        rent = 0

    if not title or not location or not owner or rent < 500:
        return jsonify({"error": "Valid details zaroori hain."}), 400

    if not owner_key:
        owner_key = "key_" + uuid.uuid4().hex[:6]

    video_url = ""
    video_file = request.files.get("video")
    if video_file and video_file.filename:
        ext = os.path.splitext(video_file.filename)[1].lower()
        if ext in [".mp4", ".webm", ".ogg", ".mov"]:
            safe_name = f"{uuid.uuid4().hex}{ext}"
            video_file.save(os.path.join(UPLOAD_DIR, safe_name))
            video_url = f"http://127.0.0.1:5000/upload/{safe_name}"

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO rooms (title, category, location, rent, amenities, video_url, owner, owner_key, saved_by_owner)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (title, category, location, rent, amenities, video_url, owner, owner_key))
    conn.commit()
    new_id = cur.lastrowid
    row = conn.execute("SELECT * FROM rooms WHERE id = ?", (new_id,)).fetchone()
    conn.close()

    return jsonify({"room": serialize_room(row), "ownerKey": owner_key}), 201


@app.route("/api/rooms/<int:room_id>/save", methods=["PATCH"])
def toggle_save_room(room_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Room nahi mila."}), 404
    new_val = 0 if row["saved_by_owner"] else 1
    conn.execute("UPDATE rooms SET saved_by_owner = ? WHERE id = ?", (new_val, room_id))
    conn.commit()
    updated = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    conn.close()
    return jsonify(serialize_room(updated))


@app.route("/api/rooms/<int:room_id>", methods=["PUT"])
def update_room(room_id):
    owner_key = request.form.get("owner_key", "").strip()
    if not owner_key:
        return jsonify({"error": "Owner Secret Key zaroori hai."}), 403

    conn = get_db()
    row = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Room nahi mila."}), 404
    if row["owner_key"] != owner_key:
        conn.close()
        return jsonify({"error": "Aap sirf apne room ko edit kar sakte hain."}), 403

    title = request.form.get("title", row["title"]).strip()
    category = request.form.get("category", row["category"]).strip()
    location = request.form.get("location", row["location"]).strip()
    owner = request.form.get("owner", row["owner"]).strip()
    amenities = request.form.get("amenities", row["amenities"]).strip()
    try:
        rent = int(request.form.get("rent", row["rent"]))
    except ValueError:
        rent = row["rent"]

    video_url = row["video_url"]
    video_file = request.files.get("video")
    if video_file and video_file.filename:
        ext = os.path.splitext(video_file.filename)[1].lower()
        if ext in [".mp4", ".webm", ".ogg", ".mov"]:
            safe_name = f"{uuid.uuid4().hex}{ext}"
            video_file.save(os.path.join(UPLOAD_DIR, safe_name))
            video_url = f"http://127.0.0.1:5000/upload/{safe_name}"

    conn.execute("""
        UPDATE rooms
        SET title = ?, category = ?, location = ?, rent = ?, amenities = ?, video_url = ?, owner = ?
        WHERE id = ?
    """, (title, category, location, rent, amenities, video_url, owner, room_id))
    conn.commit()
    updated = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    conn.close()
    return jsonify(serialize_room(updated))


@app.route("/api/rooms/<int:room_id>", methods=["DELETE"])
def delete_room(room_id):
    data = request.get_json(silent=True) or {}
    owner_key = str(data.get("owner_key", "")).strip()
    if not owner_key:
        return jsonify({"error": "Owner Secret Key zaroori hai."}), 403

    conn = get_db()
    row = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Room nahi mila."}), 404
    if row["owner_key"] != owner_key:
        conn.close()
        return jsonify({"error": "Aap sirf apne room ko delete kar sakte hain."}), 403

    conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Room delete ho gaya."})


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)