import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "../App.jsx";
import { FileText, Trash2 } from "lucide-react";
import { createPortal } from "react-dom";
import { useAuth } from "../Contexts/AuthContext";
import Header from "../Components/Header.jsx";
import Card from "../Components/Card.jsx";
import { Button } from "../Components/Button.jsx";
import Spinner from "../Components/Spinner.jsx";
import { useToast } from "../Contexts/ToastContext";
import Modal from "../Components/Modal.jsx";
import { downloadReportPdf } from "../utils/reportPdf";
import "./Pages.css";

const ReportDetailsPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { authFetch } = useAuth();
  const { addToast } = useToast();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
  const [pendingDeleteId, setPendingDeleteId] = useState(null);

  const readResponseData = async (response) => {
    const text = await response.text();
    if (!text) return {};

    try {
      return JSON.parse(text);
    } catch {
      return { error: text };
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await authFetch(`/api/reports/${id}`);
        if (!cancelled) {
          if (res.ok) {
            setReport(await res.json());
          } else {
            const err = await readResponseData(res);
            addToast(err.error || err.message || "Report not found", "error");
            navigate("/history");
          }
        }
      } catch {
        if (!cancelled) {
          addToast("Failed to load report", "error");
          navigate("/history");
        }
      }
      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [id, authFetch]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDownload = async () => {
    try {
      await downloadReportPdf(authFetch, report.id, report.reportId);
      addToast("Report downloaded successfully", "success");
    } catch (err) {
      addToast(err.message || "Failed to download PDF", "error");
    }
  };

  const confirmDelete = async () => {
    if (!pendingDeleteId) return;

    const reportId = pendingDeleteId;
    setDeletingId(reportId);
    try {
      const res = await authFetch(`/api/reports/${reportId}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Failed to delete report");
      }
      addToast("Report deleted successfully", "success");
      navigate("/history");
    } catch (err) {
      addToast(err.message || "Failed to delete report", "error");
    } finally {
      setDeletingId(null);
      setPendingDeleteId(null);
    }
  };

  if (loading) {
    return (
      <div className="report-details-page">
        <Header />
        <div className="report-details-container">
          <div className="section-loader">
            <Spinner size={36} />
            <p>Loading report…</p>
          </div>
        </div>
      </div>
    );
  }

  if (!report) return null;

  return (
    <>
      <div className="report-details-page">
        <Header />
        <div className="report-details-container">
          <button className="back-button" onClick={() => navigate("/history")}>
            ← Back to Reports
          </button>

          <div className="report-header">
            <h1>{report.reportName || "Scan Report"}</h1>
            <span className="report-date">{report.date}</span>
          </div>

          <div className="report-content">
            <div className="report-main">
              <Card className="report-image-section">
                <h2>Analyzed Image</h2>
                <div className="report-image-preview">
                  <div className="image-placeholder">🦷</div>
                  <div className="highlight-overlay">
                    <span className="highlight-marker">⚠️</span>
                  </div>
                </div>
              </Card>

              <Card className="report-findings">
                <h2>Clinical Findings</h2>
                <div className="finding-item">
                  <strong>Primary Finding:</strong>
                  <p>{report.findings}</p>
                </div>
                <div className="finding-item">
                  <strong>Recommendations:</strong>
                  <p>{report.recommendations}</p>
                </div>
              </Card>
            </div>

            <div className="report-sidebar">
              <Card className="metrics-card">
                <h3>Analysis Metrics</h3>
                <div className="metric-item">
                  <span className="metric-label">Severity Level</span>
                  <span
                    className={`severity-badge severity-${report.severity.toLowerCase()}`}
                  >
                    {report.severity}
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Confidence Score</span>
                  <span className="metric-value">
                    {Math.round(
                      report.averageConfidence ?? report.confidence ?? 0,
                    )}
                    %
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Analysis Time</span>
                  <span className="metric-value">{report.analysisDuration}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Image Size</span>
                  <span className="metric-value">{report.imageSize}</span>
                </div>
              </Card>

              <div className="report-actions">
                <Button onClick={handleDownload}>
                  <FileText size={18} /> Download PDF
                </Button>
                <Button variant="outline" onClick={() => navigate("/dashboard")}>
                  Dashboard
                </Button>
                <Button
                  variant="outline"
                  className="delete-action-btn"
                  onClick={() => setPendingDeleteId(id)}
                  disabled={deletingId === id}
                >
                  <Trash2 size={18} />
                  {deletingId === id ? "Deleting..." : "Delete"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {createPortal(
        <Modal
          isOpen={Boolean(pendingDeleteId)}
          onClose={() => {
            if (!deletingId) setPendingDeleteId(null);
          }}
          title="Confirm Delete"
          size="sm"
          closeOnOverlay={!deletingId}
          closeOnEsc={!deletingId}
          hideCloseButton={Boolean(deletingId)}
        >
          <div className="logout-confirmation">
            <p>Are you sure you want to delete this report?</p>
            <div className="modal-actions">
              <Button
                variant="outline"
                onClick={() => setPendingDeleteId(null)}
                disabled={Boolean(deletingId)}
              >
                Cancel
              </Button>
              <Button
                onClick={confirmDelete}
                loading={Boolean(deletingId)}
                loadingText="Deleting..."
              >
                Confirm Delete
              </Button>
            </div>
          </div>
        </Modal>,
        document.body,
      )}
    </>
  );
};
export default ReportDetailsPage;
