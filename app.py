import os
import sys
import json
import random
import requests
import pandas as pd
import uuid
import asyncio
import subprocess
import tempfile
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="BharatExamFest Result Portal")

# Add Session Middleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "nation-builder-secret-key-2025"))


# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize Templates
templates = Jinja2Templates(directory="templates")
# CSV / Google Sheets Configuration
GSHEET_ID = os.getenv("GSHEET_ID", "1vlL61b-u3r8eJ9JQDNdfSBFz3JrkuER_pW2AUjfpw30")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "google_credentials.json")

# SMS / OTP Configuration — 4 keys, each capped at 50 SMS/day
SMS_DAILY_LIMIT = 50
SMS_COUNTER_FILE = "sms_counters.json"

TEXTBEE_GATEWAYS = [
    {"key": os.getenv("TEXTBEE_API_KEY1", ""), "device": os.getenv("TEXTBEE_DEVICE_ID1", ""), "owner": "harshil_scet"},
    {"key": os.getenv("TEXTBEE_API_KEY2", ""), "device": os.getenv("TEXTBEE_DEVICE_ID2", ""), "owner": "parthhk"},
    {"key": os.getenv("TEXTBEE_API_KEY3", ""), "device": os.getenv("TEXTBEE_DEVICE_ID3", ""), "owner": "harshilhk"},
    {"key": os.getenv("TEXTBEE_API_KEY4", ""), "device": os.getenv("TEXTBEE_DEVICE_ID4", ""), "owner": "tishahk"},
]

# ---------------------------------------------------------------------------
# In-memory OTP store  {phone_number: otp_string}
otp_store: dict[str, str] = {}

# In-memory PDF Token store {token: student_idx}
pdf_tokens: dict[str, int] = {}

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class SendOtpRequest(BaseModel):
    phone_number: str        # 10-digit Indian number (without +91)

class VerifyOtpRequest(BaseModel):
    phone_number: str
    otp: str
    row_index: int           # DataFrame row index to save phone on success

# ---------------------------------------------------------------------------
# Helper: Google Sheets Client
# ---------------------------------------------------------------------------
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_PATH, scope)
    return gspread.authorize(creds)

# ---------------------------------------------------------------------------
# Helper: Load data from Google Sheets (with in-memory cache, TTL = 5 min)
# ---------------------------------------------------------------------------
import time as _time
_sheet_cache = {"df": None, "ts": 0.0}
CACHE_TTL = 300  # seconds

def load_data():
    now = _time.time()
    if _sheet_cache["df"] is not None and (now - _sheet_cache["ts"]) < CACHE_TTL:
        print("[Cache] Serving data from in-memory cache.")
        return _sheet_cache["df"]
    try:
        print("[Cache] Fetching fresh data from Google Sheets...")
        client = get_gsheet_client()
        sheet = client.open_by_key(GSHEET_ID).sheet1
        data = sheet.get_all_values()
        if not data: return None
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        df = df.fillna("")
        _sheet_cache["df"] = df
        _sheet_cache["ts"] = now
        print(f"[Cache] Loaded {len(rows)} rows. Cache valid for {CACHE_TTL}s.")
        return df
    except Exception as e:
        print(f"Error loading Google Sheet: {e}")
        if _sheet_cache["df"] is not None:
            print("[Cache] Returning stale cache due to error.")
            return _sheet_cache["df"]  # Serve stale data rather than failing
        return None

# ---------------------------------------------------------------------------
# Helper: Check per-phone access limit (max 5 unique students per phone)
# ---------------------------------------------------------------------------
MAX_RESULTS_PER_PHONE = 5

def check_phone_limit(phone: str, current_student_idx: int) -> tuple:
    """
    Returns (is_blocked: bool, is_already_linked: bool, linked_count: int).
    - is_already_linked = True if this phone is already saved for THIS specific student.
    - is_blocked = True if phone reached the 5-student limit AND current student is new.
    - On any error, returns (False, False, 0) so legitimate users are never blocked.
    """
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(GSHEET_ID).sheet1

        headers = sheet.row_values(1)
        if "Phone Number" not in headers:
            return False, False, 0  # Column not yet created — no restriction

        col_idx = headers.index("Phone Number") + 1
        # Fetch entire column, skip header row
        phone_col = sheet.col_values(col_idx)[1:]

        # Build list of 0-based row indices that this phone already has access to
        linked_rows = []
        for row_i, cell_val in enumerate(phone_col):
            if not cell_val:
                continue
            # Split by comma and strip whitespace / leading quote added during save
            stored_phones = [p.strip().lstrip("'") for p in cell_val.split(",")]
            if phone in stored_phones:
                linked_rows.append(row_i)

        count = len(linked_rows)
        print(f"[Limit] Phone {phone} is linked to {count} student(s). Current student idx: {current_student_idx}")

        # If this phone is already linked to THIS specific student — fast-access, no OTP needed
        if current_student_idx in linked_rows:
            print(f"[Limit] Phone already verified for this student — fast access granted.")
            return False, True, count

        # New student — block if limit reached
        if count >= MAX_RESULTS_PER_PHONE:
            print(f"[Limit] Blocked — limit of {MAX_RESULTS_PER_PHONE} reached.")
            return True, False, count

        return False, False, count

    except Exception as e:
        print(f"[Limit] Error checking phone limit: {e}")
        return False, False, 0  # Fail open so legitimate users aren't blocked by a GSheets error

# ---------------------------------------------------------------------------
# Helper: Load / save daily SMS counters from disk
# ---------------------------------------------------------------------------
def _load_counters() -> dict:
    today = str(date.today())
    if os.path.exists(SMS_COUNTER_FILE):
        try:
            with open(SMS_COUNTER_FILE, "r") as f:
                data = json.load(f)
            if data.get("date") == today:
                return data
        except Exception:
            pass
    # New day or missing file — reset all counters
    return {"date": today, "counts": [0] * len(TEXTBEE_GATEWAYS)}

def _save_counters(counters: dict):
    try:
        with open(SMS_COUNTER_FILE, "w") as f:
            json.dump(counters, f)
    except Exception as e:
        print(f"[SMS] Could not save counters: {e}")

# ---------------------------------------------------------------------------
# Helper: Send SMS via TextBee — sequential fallback across 4 API keys
# ---------------------------------------------------------------------------
def send_sms(to_number: str, message: str) -> bool:
    counters = _load_counters()

    for i, gateway in enumerate(TEXTBEE_GATEWAYS):
        used = counters["counts"][i]
        if used >= SMS_DAILY_LIMIT:
            print(f"[SMS] Gateway {i+1} ({gateway['owner']}) exhausted ({used}/{SMS_DAILY_LIMIT}), trying next...")
            continue

        url = f"https://api.textbee.dev/api/v1/gateway/devices/{gateway['device']}/send-sms"
        payload = {"recipients": [to_number], "message": message}
        headers = {"x-api-key": gateway["key"]}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code in [200, 201]:
                counters["counts"][i] += 1
                _save_counters(counters)
                print(f"[SMS] Sent via Gateway {i+1} ({gateway['owner']}) — {counters['counts'][i]}/{SMS_DAILY_LIMIT} used today")
                return True
            else:
                print(f"[SMS] Gateway {i+1} ({gateway['owner']}) returned {response.status_code}: {response.text}")
        except Exception as e:
            print(f"[SMS] Gateway {i+1} ({gateway['owner']}) error: {e}")

    print("[SMS] All 4 gateways exhausted or failed.")
    return False



# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def route_identify(request: Request):
    # Clear session to ensure a fresh start on every landing
    request.session.clear()
    return templates.TemplateResponse(request=request, name="identify.html")

@app.get("/verify", response_class=HTMLResponse)
async def route_verify(request: Request):
    # Check for one-time access flag
    if not request.session.get("can_access_verify"):
        return RedirectResponse(url="/")
    
    # Consume the flag so a refresh redirects to /
    request.session["can_access_verify"] = False
    return templates.TemplateResponse(request=request, name="verify.html")

@app.get("/result", response_class=HTMLResponse)
async def route_result(request: Request):
    # Check for one-time access flag
    if not request.session.get("can_access_result") and not request.session.get("is_verified"):
        return RedirectResponse(url="/")
        
    # Consume the flag so a refresh redirects to /
    request.session["can_access_result"] = False
    
    idx = request.session.get("student_idx")
    df = load_data()
    student_data = df.iloc[idx].tolist() if idx is not None and df is not None else None
    
    return templates.TemplateResponse(request=request, name="result.html", context={"student": student_data})

# ---------------------------------------------------------------------------
# PDF Generation Rendering Route (Secure Internal Use)
# ---------------------------------------------------------------------------
@app.get("/render-pdf-preview", response_class=HTMLResponse)
async def route_render_pdf_preview(request: Request, token: str = Query(...), idx: int = Query(...)):
    # Verify token
    if token not in pdf_tokens or pdf_tokens[token] != idx:
        raise HTTPException(status_code=403, detail="Invalid PDF Token")
    
    # We don't delete token immediately because Playwright might need it for static assets 
    # (actually static assets don't need it, so we could delete it soon after)
    
    return templates.TemplateResponse(request=request, name="result.html")

# ---------------------------------------------------------------------------
# API: Session Management & Data
# ---------------------------------------------------------------------------
@app.post("/api/select-student")
async def api_select_student(request: Request, body: dict):
    idx = body.get("row_index")
    if idx is None:
        raise HTTPException(status_code=400, detail="Missing row index")
    request.session["student_idx"] = idx
    request.session["is_verified"] = False
    # Grant one-time access to the verify page
    request.session["can_access_verify"] = True
    return {"success": True}

@app.get("/api/current-student")
async def get_current_student(request: Request):
    idx = request.session.get("student_idx")
    if idx is None:
        raise HTTPException(status_code=401, detail="No student selected")

    # load_data() is now in-memory cached — this is fast after the first call
    df = load_data()
    if df is None: raise HTTPException(status_code=500)

    row = df.iloc[idx].tolist()
    return {"student": row, "row_index": idx}

# ---------------------------------------------------------------------------
# API: fetch all students from local CSV
# ---------------------------------------------------------------------------
@app.get("/api/students")
async def get_students():
    df = load_data()
    if df is None:
        raise HTTPException(status_code=500, detail="Local student data file not found or invalid")

    rows = df.values.tolist()
    return {
        "rows": rows,
        "rank_index": 50,
        "phone_index": -1
    }

# ---------------------------------------------------------------------------
# API: send OTP via real SMS
# ---------------------------------------------------------------------------
@app.post("/api/send-otp")
async def api_send_otp(body: SendOtpRequest, request: Request):
    phone = body.phone_number.strip()

    # Validate 10-digit Indian number
    if not phone.isdigit() or len(phone) != 10 or phone[0] not in "6789":
        raise HTTPException(status_code=400, detail="Invalid mobile number")

    student_idx = request.session.get("student_idx")

    if student_idx is not None:
        is_blocked, is_already_linked, linked_count = check_phone_limit(phone, student_idx)

        # FAST ACCESS: Phone already verified for this exact student — skip OTP entirely
        if is_already_linked:
            print(f"[FastAccess] Phone {phone} already verified for student {student_idx}. Bypassing OTP.")
            request.session["is_verified"] = True
            request.session["can_access_result"] = True
            # NOTE: We do NOT store student row in session — cookie has a 4KB limit.
            # load_data() is now cached in memory so the result page will load instantly.
            return {"success": True, "already_verified": True}

        # LIMIT CHECK: Block if this phone has already accessed 5 different students
        if is_blocked:
            raise HTTPException(
                status_code=429,
                detail=f"Access limit reached. One mobile number can only be used to view results for up to {MAX_RESULTS_PER_PHONE} students."
            )

    # NEW ACCESS: Send OTP via SMS
    otp = str(random.randint(100000, 999999))
    otp_store[phone] = otp

    full_number = f"+91{phone}"
    message = f"Your BharatExamFest verification OTP is: {otp}. Do not share it with anyone."

    success = send_sms(full_number, message)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to send SMS. Please try again.")

    return {"success": True, "already_verified": False, "message": f"OTP sent to +91-{phone}"}

# ---------------------------------------------------------------------------
# API: verify OTP and save phone to CSV on success
# ---------------------------------------------------------------------------
@app.post("/api/verify-otp")
async def api_verify_otp(body: VerifyOtpRequest, request: Request):
    phone = body.phone_number.strip()
    entered_otp = body.otp.strip()

    stored_otp = otp_store.get(phone)
    if stored_otp is None:
        raise HTTPException(status_code=400, detail="OTP not found. Please request a new OTP.")

    if entered_otp != stored_otp:
        raise HTTPException(status_code=400, detail="Incorrect OTP. Please try again.")

    # OTP correct — clear from store and mark session as verified
    del otp_store[phone]
    request.session["is_verified"] = True
    request.session["can_access_result"] = True

    # Save phone number to Google Sheets
    try:
        print(f"[GSheets] Attempting to save phone for row index: {body.row_index}")
        client = get_gsheet_client()
        sheet = client.open_by_key(GSHEET_ID).sheet1
        
        # Get headers from the first row
        headers = sheet.row_values(1)
        print(f"[GSheets] Current headers: {headers}")
        
        col_idx = -1
        if "Phone Number" in headers:
            col_idx = headers.index("Phone Number") + 1
        else:
            # If not found, add it to the first empty column after existing data
            col_idx = len(headers) + 1
            print(f"[GSheets] Phone Number column not found. Creating at column {col_idx}")
            sheet.update_cell(1, col_idx, "Phone Number")
        
        # DataFrame row_index is 0-based data row (row 2 in sheet)
        sheet_row = body.row_index + 2
        
        # Fetch existing value to append instead of overwrite
        existing_val = sheet.cell(sheet_row, col_idx).value or ""
        
        # Use a proper split to avoid false substring matches
        existing_phones = [p.strip().lstrip("'") for p in existing_val.split(",")] if existing_val else []
        if phone in existing_phones:
            print(f"[GSheets] Phone {phone} already exists in row {sheet_row}. Skipping append.")
        else:
            if existing_val:
                new_val = f"{existing_val}, {phone}"
            else:
                new_val = phone
            
            print(f"[GSheets] Updating Cell: Row {sheet_row}, Col {col_idx} with {new_val}")
            # Use single quote prefix to ensure Google Sheets treats it as a string
            sheet.update_cell(sheet_row, col_idx, f"'{new_val}")
            print("[GSheets] Save successful!")
        
    except Exception as e:
        print(f"[GSheets] Error saving phone: {e}")
        # We don't necessarily want to block the user if saving fails, 
        # but let's keep the exception for now to see the error.
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    return {"success": True}

# ---------------------------------------------------------------------------
# API: PDF Download via Playwright
# ---------------------------------------------------------------------------
@app.get("/api/download-result-pdf")
async def api_download_result_pdf(request: Request):
    idx = request.session.get("student_idx")
    is_verified = request.session.get("is_verified")
    
    if idx is None or not is_verified:
        raise HTTPException(status_code=401, detail="Session expired or not verified")

    # 1. Load the student data for rendering
    df = load_data()
    if df is None: raise HTTPException(status_code=500, detail="CSV not found")
    student_data = df.iloc[idx].tolist()

    # 2. Load CSS content for inlining (optional but better for standalone rendering)
    css_content = ""
    css_path = os.path.join("static", "css", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()

    # 3. Render the HTML content manually
    html_content = templates.get_template("result.html").render({
        "request": request,
        "student": student_data,
        "inlined_css": css_content,
        "is_pdf": True
    })

    # 4. Process-isolated PDF generation
    temp_dir = tempfile.gettempdir()
    input_html = os.path.join(temp_dir, f"result_{uuid.uuid4()}.html")
    output_pdf = os.path.join(temp_dir, f"result_{uuid.uuid4()}.pdf")

    try:
        # Save HTML to temporary file
        with open(input_html, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Build command to run generator script
        # We use the same python executable that is running the app
        cmd = [sys.executable, "pdf_generator.py", input_html, output_pdf]
        
        # Run subprocess with timeout
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=30,
            cwd=os.getcwd()
        )

        if result.returncode != 0:
            error_msg = result.stderr or "Unknown generator error"
            print(f"Generator Failed: {error_msg}")
            raise Exception(error_msg)

        if not os.path.exists(output_pdf):
            raise Exception("PDF file not created by generator")

        # Read the generated PDF
        with open(output_pdf, "rb") as f:
            pdf_bytes = f.read()

        # Clean up input file
        try: os.remove(input_html)
        except: pass
        try: os.remove(output_pdf)
        except: pass

        filename = f"Official_Result_{student_data[1]}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
            
    except Exception as e:
        print(f"PDF ERROR (Subprocess): {e}")
        # Cleanup on failure
        try: os.remove(input_html)
        except: pass
        try: os.remove(output_pdf)
        except: pass
        raise HTTPException(status_code=500, detail=f"PDF Generation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    host = os.getenv("HOST", "")
    port = int(os.getenv("PORT", ""))
    uvicorn.run("app:app", host=host, port=port, reload=debug_mode)
