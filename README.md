# DentalAI

DentalAI is an AI-assisted dental caries detection platform. A React web client lets an authenticated user upload a dental image, while a Flask API runs a YOLO-based detector, stores the analysis in MongoDB, and generates a downloadable PDF report.

> **Clinical notice:** This project is an academic decision-support prototype. Its output is not a medical diagnosis and must not replace examination or advice from a licensed dental professional.

## Features

- Email-verified registration using one-time passwords (OTPs)
- JWT-based login sessions with protected user data
- Dental image upload and AI-assisted caries detection
- Detection counts, confidence levels, findings, recommendations, and verdicts
- Annotated images embedded in generated PDF reports
- Dashboard statistics and report history
- Report details, PDF download, and report deletion
- Profile editing, password changes, password reset, and account deletion
- SMTP and Brevo API email delivery options

## Architecture

```text
React + Vite frontend (port 5173)
              |
              | Vite proxy: /auth and /api
              v
Flask backend (port 5000)
       |                 |
       v                 v
  MongoDB Atlas      YOLO model (best.pt)
       |
       v
Generated PDF reports in Backend/generated_reports/
```

### Main directories

| Path | Purpose |
| --- | --- |
| `Backend/app.py` | Flask application, CORS, error handling, and server startup |
| `Backend/auth.py` | Registration, OTP, login, profile, password, and account routes |
| `Backend/api.py` | Protected upload, prediction, dashboard, and report routes |
| `Backend/model_loader.py` | Loads `Backend/best.pt` with Ultralytics YOLO |
| `Backend/reporting.py` | Detection summaries, annotated images, and PDF generation |
| `Backend/db.py` | MongoDB connection and `users`/`scans` collections |
| `Backend/generated_reports/` | Generated report PDFs |
| `Frontend/src/Pages/` | React application pages and user workflows |
| `Frontend/src/Contexts/` | Authentication and toast state |
| `Frontend/vite.config.js` | Frontend dev server and backend proxy configuration |

## Requirements

- Python 3.12 recommended
- Node.js and npm
- MongoDB Atlas or another reachable MongoDB deployment
- A valid YOLO model at `Backend/best.pt`
- An email provider for registration and password-reset OTPs, unless using local `DEV_MODE`

The model files are binary assets and are expected to be present in the repository. `Backend/convnext_dental_model.pth` is also included for the project, but the current API inference path loads `Backend/best.pt`.

## Configuration

Create `Backend/.env`. Never commit real credentials, API keys, database URIs, or production secrets.

```env
# Required
MONGO_URI=mongodb+srv://<username>:<password>@<cluster>/<database>
SECRET_KEY=replace-with-a-long-random-secret

# Optional database name when the URI does not include one
MONGO_DB=iads

# Frontend origin allowed by Flask CORS
FRONTEND_ORIGIN=http://localhost:5173

# Local-only OTP fallback. Do not enable in production.
DEV_MODE=false

# Email sender identity (required for either transport)
SENDER_EMAIL=no-reply@example.com
SENDER_NAME=DentalAI

# SMTP transport (primary when all three connection values are present)
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=your-smtp-login
SMTP_PASS=your-smtp-password-or-app-password

# Optional Brevo HTTP API fallback
BREVO_API_KEY=your-brevo-api-key
```

The email module tries SMTP first and then the Brevo HTTP API. For Gmail, use an app password rather than the normal account password. When `DEV_MODE=true`, registration and password-reset responses include the OTP for local testing; keep this disabled outside development.

## Installation

From the repository root in PowerShell:

```powershell
# Backend environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r Backend\requirements.txt

# Frontend dependencies
Set-Location Frontend
npm install
Set-Location ..
```

On Windows, `Backend/app.py` automatically re-launches itself with the repository `.venv` interpreter when that environment exists. If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

## Running locally

### Recommended: start both applications

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
```

Then open [http://localhost:5173](http://localhost:5173). The script starts the Flask API on `http://127.0.0.1:5000` and Vite on `http://localhost:5173`, and stops both processes when you press a key in its window.

### Manual startup

Run these commands in two terminals from the repository root.

**Terminal 1: backend**

```powershell
Set-Location Backend
..\.venv\Scripts\python.exe app.py
```

**Terminal 2: frontend**

```powershell
Set-Location Frontend
npm run dev
```

The Vite development proxy forwards `/auth/*` and `/api/*` requests to port 5000. The backend root health response is available at [http://127.0.0.1:5000/](http://127.0.0.1:5000/).

## User workflow

1. Open the frontend and create an account.
2. Retrieve the six-digit OTP from email, or from the response/logs when `DEV_MODE=true`.
3. Complete registration and log in.
4. Upload a supported dental image from the dashboard.
5. Review the detection summary and generated report.
6. Open report history to view details, download the PDF, or delete a report.

Uploaded files must use one of these extensions: `png`, `jpg`, `jpeg`, `bmp`, `dicom`, `dcm`, `tiff`, or `tif`. The maximum upload size is 10 MB. The API validates and decodes the image before inference.

## API reference

All protected routes require:

```http
Authorization: Bearer <jwt-token>
```

### Authentication and account routes

| Method | Endpoint | Description | Auth |
| --- | --- | --- | --- |
| `POST` | `/auth/register-start` | Create a pending account and send a verification OTP | No |
| `POST` | `/auth/register-complete` | Verify the OTP and set the password | No |
| `POST` | `/auth/login` | Log in and receive a JWT | No |
| `GET` | `/auth/me` | Get the current user | Yes |
| `PUT` | `/auth/profile` | Update `name`, `age`, or `gender` | Yes |
| `POST` | `/auth/change-password` | Change the current password | Yes |
| `DELETE` | `/auth/delete-account` | Delete the account and its reports | Yes |
| `POST` | `/auth/forgot-start` | Send a password-reset OTP | No |
| `POST` | `/auth/forgot-verify-otp` | Verify a password-reset OTP | No |
| `POST` | `/auth/forgot-reset` | Set a new password | No |
| `POST` | `/auth/test-email` | Send a diagnostic email | No |

### Analysis and report routes

| Method | Endpoint | Description | Auth |
| --- | --- | --- | --- |
| `GET` | `/api/dashboard-stats` | Return scan totals, average confidence, and recent reports | Yes |
| `POST` | `/api/upload` | Analyze an image, save the scan, and generate a PDF | Yes |
| `POST` | `/api/predict` | Run prediction and return detections without saving a report | No |
| `GET` | `/api/reports` | List the signed-in user's reports | Yes |
| `GET` | `/api/reports/<report_id>` | Get one report and its detections | Yes |
| `GET` | `/api/reports/<report_id>/pdf` | Download a generated PDF | Yes |
| `DELETE` | `/api/reports/<report_id>` | Delete a report and its PDF | Yes |
| `POST` | `/predict` | Backward-compatible alias for `/api/predict` | No |

## Testing and checks

Run the frontend checks:

```powershell
Set-Location Frontend
npm run lint
npm run build
```

Run the backend authentication flow test:

```powershell
Set-Location Backend
..\.venv\Scripts\python.exe test_auth_routes.py
```

Run the upload and PDF integration test:

```powershell
Set-Location Backend
..\.venv\Scripts\python.exe test_api.py
```

The upload test replaces the loaded model with a small fake model so it can verify the upload and PDF pipeline without running a full inference. Both backend tests still need a reachable MongoDB instance and a configured `Backend/.env`.

Useful diagnostics:

```powershell
Set-Location Backend
..\.venv\Scripts\python.exe check_db.py
..\.venv\Scripts\python.exe check_dependencies.py
```

## Troubleshooting

### `MONGO_URI is not set` or MongoDB connection errors

Confirm that `Backend/.env` exists, contains `MONGO_URI`, and that the MongoDB deployment allows the current IP address. The application pings MongoDB during startup and exits quickly when the connection is unavailable.

### OTP email delivery fails

Set either a complete SMTP configuration plus `SENDER_EMAIL`, or `BREVO_API_KEY` plus `SENDER_EMAIL`. Check the backend console for the email module's startup diagnostics. For local work, enable `DEV_MODE=true` temporarily.

### Model loading fails

Confirm that `Backend/best.pt` exists and that the Python environment contains `torch`, `torchvision`, `ultralytics`, `numpy`, `opencv-python`, and `Pillow`. On Windows, start the backend with `.venv\Scripts\python.exe` so native ML libraries come from the same environment.

### Upload returns an error

Check that both servers are running, the request uses the multipart form-data field `image`, the extension is supported, and the file is no larger than 10 MB. The backend console contains the detailed exception for model and PDF-generation failures.

### Port already in use

The default ports are 5000 for Flask and 5173 for Vite. Stop the process using the port, or update the port and matching proxy/origin configuration in `Backend/app.py` and `Frontend/vite.config.js`.

## Security notes

- Keep `Backend/.env` out of version control and rotate any credential that has been exposed.
- Use a unique, randomly generated `SECRET_KEY` outside local development.
- Keep `DEV_MODE=false` in shared, staging, and production environments.
- Treat generated PDFs as sensitive health-related data and restrict access to the authenticated report owner.
- Do not use the model output as a standalone diagnosis.

## Frontend commands

From `Frontend/`:

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the Vite development server |
| `npm run build` | Create a production frontend build in `dist/` |
| `npm run preview` | Preview the production build locally |
| `npm run lint` | Run ESLint |
| `npm run deploy` | Publish `dist/` with `gh-pages` |

## License

No license file is currently included in this repository. Add a license before distributing the project outside its intended academic or private use.