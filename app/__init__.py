"""AstroVital application factory."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from config import VERSION, Config, load_config

from .extensions import csrf, db, limiter, migrate, sock

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_logging_configured = False


class SecretRedactor(logging.Filter):
    """Replace known secret values in log records before they are written."""

    def __init__(self, secrets: tuple[str, ...]) -> None:
        super().__init__()
        self._secrets = secrets

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        message = record.getMessage()
        redacted = message
        for secret in self._secrets:
            redacted = redacted.replace(secret, "***")
        if redacted != message:
            record.msg, record.args = redacted, None
        return True


def configure_logging(config: Config, *, to_file: bool = True) -> None:
    """Send structured log lines to stderr and (optionally) a rotating file."""
    global _logging_configured
    root = logging.getLogger()
    if _logging_configured:
        return
    root.setLevel(logging.DEBUG if config.debug else logging.INFO)
    redactor = SecretRedactor(config.secret_values())
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if to_file:
        config.instance_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(config.instance_dir / "astrovital.log", maxBytes=1_000_000, backupCount=3,
                                encoding="utf-8")
        )
    for handler in handlers:
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler.addFilter(redactor)
        root.addHandler(handler)
    _logging_configured = True


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def _register_error_handlers(app: Flask) -> None:
    messages = {
        404: ("Page not found", "That page isn't part of this mission."),
        405: ("Not allowed", "That action isn't available here."),
        429: ("Too many attempts", "Wait a minute, then try again."),
    }

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        code = error.code or 500
        title, detail = messages.get(code, ("Something went wrong", "Go back and try again."))
        if _wants_json():
            return jsonify(ok=False, error=title.lower().replace(" ", "_")), code
        return render_template("error.html", code=code, title=title, detail=detail), code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("Unhandled error on %s %s", request.method, request.path)
        if _wants_json():
            return jsonify(ok=False, error="server_error"), 500
        return render_template(
            "error.html", code=500, title="Something went wrong",
            detail="The problem is on our side, not yours. Try again in a moment.",
        ), 500


def create_app(config: Config | None = None, *, testing: bool = False) -> Flask:
    """Build the Flask app: config, extensions, blueprints and error pages."""
    config = config or load_config()
    app = Flask(__name__, instance_path=str(config.instance_dir))
    app.config.from_mapping(config.flask_mapping())
    app.config["TESTING"] = testing
    app.extensions["astrovital_config"] = config

    configure_logging(config, to_file=not testing)
    config.instance_dir.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    sock.init_app(app)

    from .landing.routes import bp as landing_bp

    app.register_blueprint(landing_bp)
    _register_error_handlers(app)

    @app.context_processor
    def inject_globals() -> dict[str, object]:
        return {"app_version": VERSION, "mission_name": config.mission_name}

    return app


def get_config(app: Flask) -> Config:
    """Return the validated ``Config`` attached to an app."""
    return app.extensions["astrovital_config"]
