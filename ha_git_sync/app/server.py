"""Ingress-only panel, CSRF-protected API and background operations."""

import json
import logging
import os
from pathlib import Path
import secrets
import threading
import uuid

from flask import Flask, jsonify, request, send_from_directory
from waitress import serve

from engine import Engine
from files import SyncError


def create_app(engine=None, testing=False):
    app = Flask(__name__, static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    app.config["TESTING"] = testing
    if engine is None:
        options = json.loads(Path("/data/options.json").read_text())
        engine = Engine(options=options)
    app.engine = engine
    csrf = secrets.token_urlsafe(32)
    job_lock = threading.Lock()
    jobs = {}
    current_job = None

    @app.before_request
    def trusted_ingress():
        # No public port is exposed. Never trust forwarded headers supplied by clients.
        if not testing and request.remote_addr != "172.30.32.2":
            return jsonify(error="Öppna panelen via Home Assistants ingress."), 403
        if request.method == "POST":
            if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), csrf):
                return jsonify(error="Panelen behöver laddas om."), 403
            if not request.is_json:
                return jsonify(error="JSON krävs."), 400

    @app.after_request
    def secure_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'"
        return response

    @app.errorhandler(SyncError)
    def sync_error(error):
        return jsonify(error=str(error)), 400

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/status")
    def status():
        active = jobs.get(current_job)
        return jsonify(csrf=csrf, active_job={"id": current_job, "action": active["action"]} if active and not active["done"] else None, **engine.status())

    @app.get("/api/jobs/<job_id>")
    def get_job(job_id):
        job = jobs.get(job_id)
        if job is None:
            return jsonify(error="Operationen hittades inte. Ladda om panelen och kontrollera status."), 404
        return jsonify(job)

    @app.post("/api/jobs")
    def start_job():
        nonlocal current_job
        body = request.get_json()
        if not isinstance(body, dict):
            return jsonify(error="Ogiltig begäran."), 400
        action = body.get("action")
        handlers = {
            "setup_key": engine.setup_key,
            "branches": engine.branches,
            "dashboards": engine.ha.dashboards,
            "configure_dashboard": lambda: engine.configure_dashboard(body.get("enabled"), body.get("url_path"), body.get("repo_file")),
            "scope_catalog": engine.scope_catalog,
            "configure_scope": lambda: engine.configure_scope(body.get("includes"), body.get("excludes", [])),
            "preview_push": lambda: engine.preview("push", body.get("branch")),
            "preview_pull": lambda: engine.preview("pull", body.get("branch"), body.get("allow_deletions", False)),
            "push": lambda: engine.push(body.get("plan_id"), body.get("message")),
            "pull": lambda: engine.pull(body.get("plan_id")),
            "restore": engine.restore,
            "restart": engine.restart,
        }
        if action not in handlers:
            return jsonify(error="Okänd operation."), 400
        if not job_lock.acquire(blocking=False):
            return jsonify(error="En operation pågår redan."), 409
        # Bound memory usage for long-running add-ons.
        while len(jobs) > 30:
            jobs.pop(next(iter(jobs)))
        job_id = uuid.uuid4().hex
        current_job = job_id
        jobs[job_id] = {"id": job_id, "action": action, "done": False}

        def worker():
            try:
                result = handlers[action]()
                jobs[job_id] = {"id": job_id, "action": action, "done": True, "result": result}
            except SyncError as error:
                jobs[job_id] = {"id": job_id, "action": action, "done": True, "error": str(error)}
            except Exception:
                # Do not log captured subprocess output or request bodies.
                logging.error("Operation %s failed unexpectedly", action)
                jobs[job_id] = {"id": job_id, "action": action, "done": True, "error": "Oväntat fel. Kontrollera återställningsstatus."}
            finally:
                job_lock.release()

        threading.Thread(target=worker, daemon=True).start()
        return jsonify(id=job_id), 202

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve(create_app(), host="0.0.0.0", port=8099, threads=4)
