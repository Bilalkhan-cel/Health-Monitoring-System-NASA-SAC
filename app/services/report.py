"""The "Downlink Report": a one-page PDF for the ground flight surgeon (Section 14).

It carries trends, flags and a session list. Mental-health content is limited to status
and trend; transcripts never appear. There is no source column anywhere.
"""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import Config

from ..models import Astronaut, Measurement, ReadinessDaily
from . import history, thresholds
from .mission import mission_day
from .readiness import load_indicators
from .summary import build_summary, duration_text, load_environments, number_text

STATUS_COLOURS = {"good": colors.HexColor("#1F9D6B"), "okay": colors.HexColor("#3D7BD9"),
                  "watch": colors.HexColor("#C98A00"), "alert": colors.HexColor("#D23A52")}
INK = colors.HexColor("#111418")
MUTED = colors.HexColor("#5A6270")
LINE = colors.HexColor("#D9DDE3")
DISCLAIMER = ("Prototype for educational purposes, inspired by the NASA Human Research Program. Not a certified "
              "medical device. Alert rules are cautious placeholders pending clinical review.")

_styles = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=INK),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8.5, leading=11, textColor=MUTED),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=INK, spaceBefore=6,
                         spaceAfter=3),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7, leading=9, textColor=MUTED),
}


def _status_label(status: str | None) -> str:
    return thresholds.STATUS_META[status]["label"] if status in thresholds.STATUS_META else "No data"


def _trend_chart(astronaut: Astronaut, today: date, days: int = 30) -> Drawing:
    start = today - timedelta(days=days - 1)
    rows = (ReadinessDaily.query.filter(ReadinessDaily.astronaut_id == astronaut.id, ReadinessDaily.date >= start,
                                        ReadinessDaily.date <= today, ReadinessDaily.score.isnot(None))
            .order_by(ReadinessDaily.date).all())
    readiness = [((row.date - start).days, row.score) for row in rows]
    wellbeing_rows = (Measurement.query.filter(Measurement.astronaut_id == astronaut.id,
                                               Measurement.metric == "wellbeing",
                                               Measurement.created_at >= datetime.combine(start, datetime.min.time()))
                      .order_by(Measurement.created_at).all())
    wellbeing = [((row.created_at.date() - start).days, row.value) for row in wellbeing_rows]
    drawing = Drawing(170 * mm, 42 * mm)
    if not readiness and not wellbeing:
        drawing.add(String(0, 20 * mm, "Not enough data for a trend yet.", fontName="Helvetica", fontSize=8,
                           fillColor=MUTED))
        return drawing
    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = 10 * mm, 6 * mm, 150 * mm, 32 * mm
    series = [data for data in (readiness, wellbeing) if data]
    plot.data = series
    plot.xValueAxis.valueMin, plot.xValueAxis.valueMax = 0, days - 1
    plot.xValueAxis.valueSteps = [0, days // 2, days - 1]
    plot.xValueAxis.labelTextFormat = lambda value: (start + timedelta(days=int(value))).strftime("%d %b")
    plot.yValueAxis.valueMin, plot.yValueAxis.valueMax, plot.yValueAxis.valueStep = 0, 100, 25
    for axis in (plot.xValueAxis, plot.yValueAxis):
        axis.labels.fontName, axis.labels.fontSize, axis.labels.fillColor = "Helvetica", 7, MUTED
        axis.strokeColor = LINE
    palette = [colors.HexColor("#3D7BD9"), colors.HexColor("#7C6CFF")]
    for index in range(len(series)):
        plot.lines[index].strokeColor = palette[index if readiness else 1]
        plot.lines[index].strokeWidth = 1.4
    drawing.add(plot)
    legend_x = 12 * mm
    for name, colour, present in (("Readiness", palette[0], bool(readiness)),
                                  ("Mental wellbeing", palette[1], bool(wellbeing))):
        if present:
            drawing.add(String(legend_x, 39.5 * mm, f"— {name}", fontName="Helvetica", fontSize=7.5,
                               fillColor=colour))
            legend_x += 32 * mm
    return drawing


def _table(rows: list[list], widths: list[float], status_col: int | None = None,
           status_keys: list[str | None] | None = None) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 7.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, LINE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
    ]
    if status_col is not None and status_keys:
        for index, key in enumerate(status_keys, start=1):
            if key in STATUS_COLOURS:
                style.append(("TEXTCOLOR", (status_col, index), (status_col, index), STATUS_COLOURS[key]))
                style.append(("FONT", (status_col, index), (status_col, index), "Helvetica-Bold", 7.5))
    table.setStyle(TableStyle(style))
    return table


def build_pdf(astronaut: Astronaut, config: Config, now: datetime) -> bytes:
    """Render the report and return the PDF bytes."""
    payload = build_summary(astronaut, config, now)
    spec = load_indicators()["metrics"]
    mission = astronaut.mission
    environment = load_environments().get(mission.environment, {})
    delay = mission.comms_delay_s if mission.comms_delay_s is not None else environment.get("comms_delay_one_way_s", 0)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=12 * mm, title=f"Downlink Report {astronaut.astro_id}",
                            author="AstroVital")
    story: list = []
    story.append(Paragraph("Downlink Report", _styles["title"]))
    story.append(Paragraph(escape(
        f"{astronaut.name} ({astronaut.astro_id}) · {astronaut.role} · {mission.name} · "
        f"Day {mission_day(config, mission)} · {mission.environment} · one-way comms delay {duration_text(delay)} · "
        f"generated {now:%Y-%m-%d %H:%M} UTC"), _styles["meta"]))
    story.append(Spacer(1, 4 * mm))

    readiness = payload.get("readiness") or {}
    score = readiness.get("score")
    status = (readiness.get("status") or {}).get("label") if isinstance(readiness.get("status"), dict) else None
    headline = f"Readiness {score:.0f}/100" if isinstance(score, (int, float)) else "Readiness: not enough data"
    sentence = readiness.get("sentence") or (f"{status}." if status else "")
    story.append(Paragraph(f"<b>{headline}</b> · {escape(sentence)}", _styles["body"]))

    story.append(Paragraph("Trend, last 30 days", _styles["h2"]))
    story.append(_trend_chart(astronaut, now.date()))

    story.append(Paragraph("Latest readings", _styles["h2"]))
    rows, keys = [["Indicator", "Latest", "Usual", "Status", "When"]], []
    for item in payload.get("metrics", []):
        if item.get("key") not in spec:
            continue
        item_status = item.get("status") or {}
        keys.append(item_status.get("key"))
        unit = item.get("unit") or ""
        value = (f"{item['value']}{unit}" if unit.startswith("/") else f"{item['value']} {unit}".strip())             if item.get("value") is not None else "—"
        usual = Paragraph(escape(item["usual"]), _styles["body"]) if item.get("usual") else "—"
        updated = (item.get("updated") or "—").replace("Updated ", "")
        rows.append([spec[item["key"]]["short"], value, usual, item_status.get("label") or "No data", updated])
    story.append(_table(rows, [30 * mm, 28 * mm, 62 * mm, 30 * mm, 28 * mm], 3, keys))

    story.append(Paragraph("Flags, last 7 days", _styles["h2"]))
    since = now - timedelta(days=7)
    flagged = (Measurement.query.filter(Measurement.astronaut_id == astronaut.id, Measurement.created_at >= since,
                                        Measurement.status.in_(("CAUTION", "CRITICAL")))
               .order_by(Measurement.created_at.desc()).all())
    seen, flag_rows, flag_keys = set(), [["When (UTC)", "Indicator", "Reading", "Status"]], []
    for row in flagged:
        if row.metric not in spec or (row.metric, row.created_at.date(), row.status) in seen:
            continue
        seen.add((row.metric, row.created_at.date(), row.status))
        flag_keys.append(thresholds.STATUS_META[row.status]["key"])
        flag_rows.append([f"{row.created_at:%d %b %H:%M}", spec[row.metric]["short"],
                          number_text(row.metric, row.value, row.value2), _status_label(row.status)])
        if len(flag_rows) > 10:
            break
    if len(flag_rows) == 1:
        story.append(Paragraph("No readings needed attention.", _styles["body"]))
    else:
        story.append(_table(flag_rows, [34 * mm, 40 * mm, 50 * mm, 54 * mm], 3, flag_keys))

    story.append(Paragraph("Sessions, last 7 days", _styles["h2"]))
    filters = history.Filters(start=now.date() - timedelta(days=6), end=now.date())
    session_rows, session_keys = [["When (UTC)", "Session", "Result", "Status"]], []
    for day in history.timeline(astronaut, filters):
        for entry in day["entries"]:
            text = entry["text"]
            if entry["kind"] == "checkin":  # status and score only, never what was said
                text = text.split(".")[0] + "."
            session_rows.append([f"{entry['at'][:10]} {entry['time'] or ''}".strip(), entry["title"],
                                 Paragraph(escape(text[:140]), _styles["body"]),
                                 entry["status"]["label"] if entry["status"] else "—"])
            session_keys.append(entry["status"]["key"] if entry["status"] else None)
    session_rows = session_rows[:13]
    session_keys = session_keys[:12]
    if len(session_rows) == 1:
        story.append(Paragraph("No sessions in the last 7 days.", _styles["body"]))
    else:
        story.append(_table(session_rows, [30 * mm, 32 * mm, 82 * mm, 34 * mm], 3, session_keys))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(DISCLAIMER, _styles["small"]))
    doc.build(story)
    return buffer.getvalue()
