"""/history and its exports (Section 14). Every route reads only the logged-in astronaut's data."""

from __future__ import annotations

from datetime import date

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request

from ..auth.decorators import login_required
from ..auth.services import current_crew
from ..models import utcnow
from ..services import history, report
from ..services.readiness import load_indicators

bp = Blueprint("history", __name__)

SYSTEM_LABELS = {"all": "All", "cardio": "Heart", "bones": "Bones & muscle", "mental": "Mind", "sleep": "Sleep"}
KIND_LABELS = {"all": "All types", "heart_check": "Heart checks", "exercise": "Exercise", "checkin": "Check-ins",
               "sleep": "Sleep logs"}
STATUS_LABELS = {"all": "Any status", "good": "Good", "okay": "Okay", "watch": "Needs attention",
                 "alert": "Get help now"}
CHART_METRICS = ("readiness", "heart_rate", "blood_pressure", "spo2", "temperature_c", "glucose", "respiration",
                 "sleep_hours", "wellbeing", "loading_index")


def _filters() -> history.Filters:
    return history.Filters.parse(request.args, utcnow().date())


@bp.get("/history")
@login_required
def index():
    crew, filters = current_crew(), _filters()
    spec = load_indicators()["metrics"]
    metrics = [{"key": key, "label": "Readiness" if key == "readiness" else spec[key]["short"]}
               for key in CHART_METRICS]
    return render_template(
        "history.html", filters=filters, query=filters.as_query(), timeline=history.timeline(crew, filters),
        heatmap=history.heatmap(crew, filters), metrics=metrics, systems=SYSTEM_LABELS, kinds=KIND_LABELS,
        statuses=STATUS_LABELS)


@bp.get("/history/day/<day>")
@login_required
def day_detail(day: str):
    try:
        when = date.fromisoformat(day)
    except ValueError:
        abort(404)
    return jsonify(history.day_detail(current_crew(), when))


@bp.get("/history/export.csv")
@login_required
def export_csv():
    crew, filters = current_crew(), _filters()
    name = f"astrovital-{crew.astro_id}-{filters.start:%Y%m%d}-{filters.end:%Y%m%d}.csv"
    return Response(history.csv_text(crew, filters), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@bp.get("/history/report.pdf")
@login_required
def report_pdf():
    crew, now = current_crew(), utcnow()
    pdf = report.build_pdf(crew, current_app.extensions["astrovital_config"], now)
    name = f"downlink-report-{crew.astro_id}-{now:%Y%m%d}.pdf"
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})
