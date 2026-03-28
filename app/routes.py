from flask import Blueprint, render_template, current_app, jsonify
from app import mongo_client

main = Blueprint("main", __name__)


@main.route("/")
def home():
    return render_template("home.html", project_name="LegalEase")


@main.route("/health")
def health():
    try:
        mongo_client.admin.command("ping")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return jsonify({
        "app": "LegalEase",
        "status": "running",
        "database": db_status,
        "upload_folder": current_app.config["UPLOAD_FOLDER"]
    })