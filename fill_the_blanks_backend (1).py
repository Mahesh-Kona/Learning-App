from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os, re, json

# ---------------- APP SETUP ----------------

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///activities.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

db = SQLAlchemy(app)

# ---------------- DATABASE ----------------

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))
    type = db.Column(db.String(50))
    instructions = db.Column(db.Text)
    content = db.Column(db.Text)
    blanks = db.Column(db.Text)
    media = db.Column(db.String(255))

with app.app_context():
    db.create_all()
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- HELPERS ----------------

def extract_blanks(text):
    return re.findall(r"\[\[(.*?)\]\]", text)

def get_payload():
    if request.is_json:
        return request.json
    return request.form

# ---------------- ROUTES ----------------

@app.route("/activity/save", methods=["POST"])
def save_activity():
    data = get_payload()
    file = request.files.get("media")

    content = data.get("content", "")
    blanks = extract_blanks(content)

    activity = Activity.query.first()
    if not activity:
        activity = Activity()

    activity.title = data.get("title", "")
    activity.type = data.get("activity_type", "")
    activity.instructions = data.get("instructions", "")
    activity.content = content
    activity.blanks = json.dumps(blanks)

    if file:
        path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(path)
        activity.media = file.filename

    db.session.add(activity)
    db.session.commit()

    return jsonify({
        "success": True,
        "blanks": blanks
    })


@app.route("/activity/load", methods=["GET"])
def load_activity():
    activity = Activity.query.first()
    if not activity:
        return jsonify({"success": False})

    return jsonify({
        "title": activity.title,
        "activity_type": activity.type,
        "instructions": activity.instructions,
        "content": activity.content,
        "blanks": json.loads(activity.blanks or "[]"),
        "media": activity.media
    })


@app.route("/activity/preview", methods=["POST"])
def preview_activity():
    data = get_payload()
    content = data.get("content", "")

    blanks = extract_blanks(content)
    preview = re.sub(r"\[\[(.*?)\]\]", "_____", content)

    return jsonify({
        "preview": preview,
        "blanks": blanks
    })


@app.route("/activity/delete", methods=["DELETE"])
def delete_activity():
    activity = Activity.query.first()
    if activity:
        db.session.delete(activity)
        db.session.commit()

    return jsonify({"success": True})


@app.route("/activity/export", methods=["GET"])
def export_activity():
    activity = Activity.query.first()
    if not activity:
        return jsonify({"error": "No activity found"})

    return jsonify({
        "title": activity.title,
        "type": activity.type,
        "instructions": activity.instructions,
        "content": activity.content,
        "answers": json.loads(activity.blanks)
    })


@app.route("/media/<filename>")
def serve_media(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)
