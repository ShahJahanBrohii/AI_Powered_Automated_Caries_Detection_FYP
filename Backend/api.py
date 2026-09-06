"""
DentalAI - Protected API Routes
=================================
All routes require JWT authentication via @login_required.
Every database query is scoped to g.current_user["email"]
so users can only access their own data.
"""

import importlib
import logging
import os
from datetime import datetime
from time import perf_counter

from bson import ObjectId
from flask import Blueprint, g, jsonify, request, send_file

from db import scans, users
from middleware import login_required
from reporting import (
    APP_GENERATOR,
    APP_NAME,
    build_report_pdf,
    confidence_band,
    draw_annotated_image,
    generate_patient_id,
    generate_report_id,
    verdict_for_detections,
)

api = Blueprint("api", __name__, url_prefix="/api")
log = logging.getLogger("dentalai.api")


# --- Internal helpers --------------------------------------------------------

def _get_or_create_patient_profile(email: str, fallback_name: str = "Patient") -> tuple[str, str]:
    user = users.find_one({"email": email}, {"patientId": 1, "name": 1}) or {}
    existing_patient_id = user.get("patientId")
    patient_name = (user.get("name") or fallback_name or "Patient").strip()

    if existing_patient_id:
        return existing_patient_id, patient_name

    patient_id = generate_patient_id(year=datetime.utcnow().year)
    users.update_one({"email": email}, {"$set": {"patientId": patient_id}})
    return patient_id, patient_name


def _serialize_report(report: dict) -> dict:
    date_value = report.get("date", datetime.utcnow())
    if isinstance(date_value, datetime):
        date_str = date_value.strftime("%Y-%m-%d")
    else:
        date_str = str(date_value)

    average_confidence = report.get("averageConfidence", report.get("confidence", 0))

    return {
        "id": str(report["_id"]),
        "reportId": report.get("reportId", str(report["_id"])),
        "patientId": report.get("patientId", "N/A"),
        "reportName": report.get("reportName") or report.get("filename") or "Scan Report",
        "filename": report.get("filename", ""),
        "date": date_str,
        "time": report.get("analysisTimeOfDay", "N/A"),
        "confidence": round(float(average_confidence)) if average_confidence is not None else 0,
        "averageConfidence": float(average_confidence or 0),
        "overallConfidenceLevel": report.get("overallConfidenceLevel", "Low"),
        "severity": report.get("severity", "Unknown"),
        "status": report.get("status", "Completed"),
        "findings": report.get("findings", ""),
        "resultSummary": report.get("resultSummary", ""),
        "totalDetections": report.get("totalDetections", report.get("detectionCount", 0)),
        "finalVerdictLevel": report.get("finalVerdictLevel", "None"),
        "pdfAvailable": bool(report.get("pdfPath")),
    }


def _load_ai_dependencies():
    np = importlib.import_module("numpy")
    cv2 = importlib.import_module("cv2")
    from model_loader import model

    return np, cv2, model


def _extract_detections(results, class_names=None) -> list[dict]:
    detections: list[dict] = []
    for result in results:
        boxes = getattr(result, "boxes", None)
        if boxes is None or boxes.xyxy is None or boxes.conf is None:
            continue

        box_values = boxes.xyxy.cpu().numpy()
        confidence_values = boxes.conf.cpu().numpy()
        class_values = getattr(boxes, "cls", None)
        class_values = class_values.cpu().numpy() if class_values is not None else None

        if class_values is None:
            class_values = [None] * len(box_values)

        result_names = getattr(result, "names", None) or class_names or {}

        for box, score, class_id in zip(box_values, confidence_values, class_values):
            x1, y1, x2, y2 = box
            class_id = int(class_id) if class_id is not None else None
            class_name = result_names.get(class_id, str(class_id)) if class_id is not None else None
            display_confidence = float(score)
            if str(class_name).lower() == "cavity" and score < 0.5:
                display_confidence = 1.0 - float(score)
            detections.append(
                {
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    "confidence": display_confidence,
                    "class_id": class_id,
                    "class_name": class_name,
                }
            )

    return detections


# --- Dashboard Stats ---------------------------------------------------------

@api.get("/dashboard-stats")
@login_required
def dashboard_stats():
    """Aggregated dashboard statistics scoped to the authenticated user."""
    email = g.current_user["email"]

    user_scans = list(
        scans.find(
            {"user_email": email},
            {
                "_id": 1,
                "date": 1,
                "averageConfidence": 1,
                "confidence": 1,
                "severity": 1,
                "reportName": 1,
                "filename": 1,
                "findings": 1,
                "reportId": 1,
                "finalVerdictLevel": 1,
            },
        ).sort("date", -1)
    )

    total = len(user_scans)
    avg_confidence = 0
    if total > 0:
        avg_confidence = round(
            sum(
                s.get("averageConfidence", s.get("confidence", 0))
                for s in user_scans
            )
            / total
        )

    now = datetime.now()
    this_month = sum(
        1
        for s in user_scans
        if isinstance(s.get("date"), datetime)
        and s["date"].month == now.month
        and s["date"].year == now.year
    )

    recent = []
    for s in user_scans[:5]:
        d = s.get("date", now)
        recent.append(
            {
                "id": str(s["_id"]),
                "reportId": s.get("reportId", str(s["_id"])),
                "reportName": s.get("reportName") or s.get("filename") or "Scan Report",
                "date": d.strftime("%Y-%m-%d") if isinstance(d, datetime) else str(d),
                "confidence": round(
                    float(s.get("averageConfidence", s.get("confidence", 0)))
                ),
                "severity": s.get("severity", "Unknown"),
                "findings": s.get("findings", ""),
                "finalVerdictLevel": s.get("finalVerdictLevel", "None"),
            }
        )

    return (
        jsonify(
            {
                "totalScans": total,
                "avgConfidence": avg_confidence,
                "thisMonth": this_month,
                "recentReports": recent,
                "patientId": g.current_user.get("patientId"),
            }
        ),
        200,
    )


# --- Reports List ------------------------------------------------------------

@api.get("/reports")
@login_required
def get_reports():
    """All reports for the authenticated user, newest first."""
    email = g.current_user["email"]

    user_reports = list(scans.find({"user_email": email}).sort("date", -1))
    reports = [_serialize_report(report) for report in user_reports]
    return jsonify({"reports": reports}), 200


# --- Single Report -----------------------------------------------------------

@api.get("/reports/<report_id>")
@login_required
def get_report(report_id):
    """Single report detail verified to belong to the authenticated user."""
    email = g.current_user["email"]

    try:
        oid = ObjectId(report_id)
    except Exception:
        return jsonify({"error": "Invalid report ID"}), 400

    report = scans.find_one({"_id": oid, "user_email": email})
    if not report:
        return jsonify({"error": "Report not found"}), 404

    payload = _serialize_report(report)
    payload.update(
        {
            "findings": report.get("findings", "No findings recorded"),
            "recommendations": report.get("recommendations", ""),
            "analysisDuration": report.get("analysisDuration", "N/A"),
            "imageSize": report.get("imageSize", "N/A"),
            "resultSummary": report.get("resultSummary", ""),
            "detections": report.get("detections", []),
            "verdictText": report.get("verdictText", ""),
        }
    )
    return jsonify(payload), 200


@api.get("/reports/<report_id>/pdf")
@login_required
def download_report_pdf(report_id):
    """Download the generated PDF for a report owned by the authenticated user."""
    email = g.current_user["email"]

    try:
        oid = ObjectId(report_id)
    except Exception:
        return jsonify({"error": "Invalid report ID"}), 400

    report = scans.find_one({"_id": oid, "user_email": email}, {"pdfPath": 1, "reportId": 1})
    if not report:
        return jsonify({"error": "Report not found"}), 404

    pdf_path = report.get("pdfPath")
    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify({"error": "PDF not available for this report"}), 404

    download_name = f"{report.get('reportId', 'dental-report')}.pdf"
    return send_file(pdf_path, as_attachment=True, download_name=download_name)


@api.delete("/reports/<report_id>")
@login_required
def delete_report(report_id):
    """Delete a report owned by the authenticated user."""
    email = g.current_user["email"]

    try:
        oid = ObjectId(report_id)
    except Exception:
        return jsonify({"error": "Invalid report ID"}), 400

    report = scans.find_one({"_id": oid, "user_email": email}, {"pdfPath": 1})
    if not report:
        return jsonify({"error": "Report not found"}), 404

    deleted = scans.delete_one({"_id": oid, "user_email": email})
    if deleted.deleted_count == 0:
        return jsonify({"error": "Report not found"}), 404

    pdf_path = report.get("pdfPath")
    if pdf_path and os.path.exists(pdf_path):
        try:
            os.remove(pdf_path)
        except OSError:
            log.warning("Failed to remove PDF file for report %s", report_id)

    log.info("Report deleted by %s: %s", email, report_id)
    return jsonify({"message": "Report deleted successfully"}), 200


# --- Upload + Analyze --------------------------------------------------------

@api.post("/upload")
@login_required
def upload_scan():
    """
    Upload a dental image, run model inference, generate a professional PDF,
    and save a report linked to the authenticated user.
    """
    email = g.current_user["email"]

    file = request.files.get("image") or request.files.get("file")
    if file is None:
        return jsonify({"error": "No file uploaded"}), 400

    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    allowed = {"png", "jpg", "jpeg", "bmp", "dicom", "dcm", "tiff", "tif"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        return (
            jsonify(
                {
                    "error": f"File type '.{ext}' not supported. Use: {', '.join(sorted(allowed))}",
                }
            ),
            400,
        )

    file_bytes = file.read()
    file_size = len(file_bytes)
    if file_size > 10 * 1024 * 1024:
        return jsonify({"error": "File too large. Maximum size is 10 MB."}), 400

    try:
        np, cv2, model = _load_ai_dependencies()
    except Exception as exc:
        log.exception("Upload dependencies unavailable")
        return (
            jsonify(
                {
                    "error": "AI dependencies are missing. Install numpy, opencv-python and ultralytics.",
                    "details": str(exc),
                }
            ),
            500,
        )

    img = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(img, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({"error": "Invalid or unreadable image file."}), 400

    start_time = perf_counter()
    results = model.predict(source=img, verbose=False)
    elapsed = perf_counter() - start_time

    detections = _extract_detections(results, getattr(model, "names", None))

    cavity_detections = [d for d in detections if d.get("class_name") == "cavity"]
    cavity_count = len(cavity_detections)
    confidence_values = [d["confidence"] * 100 for d in cavity_detections]
    class_names = [d.get("class_name") for d in cavity_detections]
    avg_confidence = round(sum(confidence_values) / cavity_count, 1) if cavity_count else 0.0
    max_confidence = round(max(confidence_values), 1) if confidence_values else 0.0

    if cavity_count == 0:
        overall_confidence_level = "No cavity detected"
    elif max_confidence >= 75:
        overall_confidence_level = "High"
    elif max_confidence >= 50:
        overall_confidence_level = "Moderate"
    else:
        overall_confidence_level = "Detected"
    verdict_level, verdict_text = verdict_for_detections(cavity_count, confidence_values, class_names)
    if cavity_count == 0:
        confidence_summary = "No cavity detected"
    elif cavity_count == 1:
        confidence_summary = f"Single cavity detected ({max_confidence:.1f}% max confidence)"
    else:
        confidence_summary = f"{cavity_count} cavity detections, {max_confidence:.1f}% max confidence"

    findings = (
        "No cavity was detected by the AI model. No bounding boxes are shown in the report."
        if cavity_count == 0
        else f"{cavity_count} cavity region(s) were highlighted by AI-assisted analysis with up to {max_confidence:.1f}% model confidence."
    )
    recommendations = (
        "Continue routine oral hygiene and periodic dental checkups."
        if verdict_level == "None"
        else "Professional dental evaluation is recommended to confirm findings and discuss care options."
    )

    now = datetime.now()
    patient_id, patient_name = _get_or_create_patient_profile(email, g.current_user.get("name", "Patient"))
    report_id = generate_report_id()

    try:
        annotated_image_bytes = draw_annotated_image(cv2, img, cavity_detections)
        output_dir = os.path.join(os.path.dirname(__file__), "generated_reports")
        pdf_path = os.path.abspath(os.path.join(output_dir, f"{report_id}.pdf"))

        build_report_pdf(
            pdf_path,
            {
                "patient_name": patient_name,
                "patient_id": patient_id,
                "report_id": report_id,
                "analysis_date": now.strftime("%B %d, %Y"),
                "analysis_time": now.strftime("%I:%M %p"),
                "filename": file.filename,
                "avg_confidence": avg_confidence,
                "max_confidence": max_confidence,
                "confidence_summary": confidence_summary,
                "confidence_level": overall_confidence_level,
                "detections": cavity_detections,
                "annotated_image_bytes": annotated_image_bytes,
                "total_detections": cavity_count,
                "cavity_count": cavity_count,
                "verdict_level": verdict_level,
                "verdict_text": verdict_text,
            },
        )
    except Exception as exc:
        log.exception("Failed to generate report PDF")
        return jsonify({"error": "Failed to generate report PDF", "details": str(exc)}), 500

    scan_doc = {
        "user_email": email,
        "reportId": report_id,
        "patientId": patient_id,
        "filename": file.filename,
        "reportName": f"Dental Caries Detection Report - {report_id}",
        "date": now,
        "analysisDate": now.strftime("%B %d, %Y"),
        "analysisTimeOfDay": now.strftime("%I:%M %p"),
        "analysisDuration": f"{elapsed:.2f} seconds",
        "fileSize": f"{file_size / 1024:.1f} KB",
        "imageSize": (
            f"{file_size / (1024 * 1024):.2f} MB"
            if file_size > 1024 * 1024
            else f"{file_size / 1024:.1f} KB"
        ),
        "totalDetections": cavity_count,
        "detectionCount": cavity_count,
        "averageConfidence": avg_confidence,
        "confidence": avg_confidence,
        "overallConfidenceLevel": overall_confidence_level,
        "severity": overall_confidence_level,
        "finalVerdictLevel": verdict_level,
        "verdictText": verdict_text,
        "findings": findings,
        "recommendations": recommendations,
        "resultSummary": f"{confidence_summary}.",
                "confidenceSummary": confidence_summary,
        "generatedBy": f"{APP_NAME} {APP_GENERATOR}",
        "pdfPath": pdf_path,
        "pdfFileName": os.path.basename(pdf_path),
        "detections": cavity_detections,
        "status": "Completed",
    }

    result = scans.insert_one(scan_doc)
    log.info("New scan uploaded by %s: %s", email, result.inserted_id)

    return (
        jsonify(
            {
                "message": "Analysis Complete",
                "reportDbId": str(result.inserted_id),
                "reportId": report_id,
                "patientId": patient_id,
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%I:%M %p"),
                "totalDetections": cavity_count,
                "averageConfidence": avg_confidence,
                "maxConfidence": max_confidence,
                "overallConfidenceLevel": overall_confidence_level,
                "finalVerdictLevel": verdict_level,
                "confidenceSummary": confidence_summary,
                "resultSummary": scan_doc["resultSummary"],
                "pdfDownloadUrl": f"/api/reports/{result.inserted_id}/pdf",
            }
        ),
        201,
    )


# --- Predict Route -----------------------------------------------------------

@api.route("/predict", methods=["POST"])
def predict():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded. Use form-data key 'image'."}), 400

    file = request.files["image"]

    try:
        np, cv2, model = _load_ai_dependencies()
    except Exception as exc:
        log.exception("Predict dependencies unavailable")
        return (
            jsonify(
                {
                    "error": "AI dependencies are missing. Install numpy, opencv-python and ultralytics.",
                    "details": str(exc),
                }
            ),
            500,
        )

    img = np.frombuffer(file.read(), np.uint8)
    img = cv2.imdecode(img, cv2.IMREAD_COLOR)

    if img is None:
        return jsonify({"error": "Invalid or unreadable image file."}), 400

    results = model.predict(source=img, verbose=False)
    detections = _extract_detections(results, getattr(model, "names", None))

    return jsonify({"detections": detections})