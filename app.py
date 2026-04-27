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
from datetime import date
from fastapi import FastAPI, Request, HTTPException, Depends, Query, UploadFile, File
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

# ---------------------------------------------------------------------------
# Admin Security Dependency
# ---------------------------------------------------------------------------
def is_admin(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize Templates
templates = Jinja2Templates(directory="templates")
# Offline CSV Data Source
CSV_DATA_PATH = os.getenv("CSV_DATA_PATH", "Nation Builder Report Card JUNIOR - Student.csv")

# ---------------------------------------------------------------------------
# Helper: Load data from Local CSV (with in-memory cache)
# ---------------------------------------------------------------------------
import time as _time
_data_cache = {"df": None, "ts": 0.0}
CACHE_TTL = 300  # seconds
CACHE_FILE = "students_cache.json"
COLLECTED_NUMBERS_PATH = "collected_numbers.csv"

def save_collected_number(name, phone, roll_no, school):
    import csv
    from datetime import datetime
    file_exists = os.path.exists(COLLECTED_NUMBERS_PATH)
    with open(COLLECTED_NUMBERS_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Name", "Phone", "Exam Roll Number", "School"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, phone, roll_no, school])

def load_data():
    now = _time.time()
    
    # 1. Use in-memory cache if fresh
    if _data_cache["df"] is not None and (now - _data_cache["ts"]) < CACHE_TTL:
        print("[Cache] Serving data from in-memory cache.")
        return _data_cache["df"]
    
    # 2. Try to load from CSV (Primary Offline Source)
    if os.path.exists(CSV_DATA_PATH):
        try:
            print(f"[Data] Loading from CSV: {CSV_DATA_PATH}")
            df = pd.read_csv(CSV_DATA_PATH)
            df = df.fillna("")

            # Clean numeric columns that Pandas might read as floats (e.g., 6.0 -> 6)
            def clean_numeric(val):
                s = str(val).strip()
                if s.endswith(".0"):
                    return s[:-2]
                return s

            numeric_cols = ["Std.", "Roll No.", "Exam Roll Number"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = df[col].apply(clean_numeric)

            # Clean school names
            if "School Name" in df.columns:
                df["School Name"] = df["School Name"].astype(str).str.strip()
            
            _data_cache["df"] = df
            _data_cache["ts"] = now
            return df
        except Exception as e:
            print(f"[Error] Failed to load CSV: {e}")

    # 3. Fallback: try loading from JSON cache if CSV is missing
    if os.path.exists(CACHE_FILE):
        try:
            print(f"[Cache] Falling back to JSON cache: {CACHE_FILE}")
            df = pd.read_json(CACHE_FILE, orient="split")
            df = df.fillna("")

            # Clean numeric columns (e.g., 6.0 -> 6)
            def clean_numeric(val):
                s = str(val).strip()
                if s.endswith(".0"):
                    return s[:-2]
                return s

            numeric_cols = ["Std.", "Roll No.", "Exam Roll Number"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = df[col].apply(clean_numeric)

            _data_cache["df"] = df
            _data_cache["ts"] = now
            return df
        except Exception as fe:
            print(f"[Cache] Could not read JSON backup: {fe}")

    return None

# In-memory PDF Token store {token: student_idx}
pdf_tokens: dict[str, int] = {}

# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def route_identify(request: Request):
    # Clear session to ensure a fresh start on every landing
    request.session.clear()
    return templates.TemplateResponse(request=request, name="identify.html")

@app.get("/result", response_class=HTMLResponse)
async def route_result(request: Request):
    idx = request.session.get("student_idx")
    if idx is None:
        return RedirectResponse(url="/")
    
    df = load_data()
    student_data = df.iloc[idx].tolist() if idx is not None and df is not None else None
    
    return templates.TemplateResponse(request=request, name="result.html", context={"student": student_data})

# ---------------------------------------------------------------------------
# Admin Routes
# ---------------------------------------------------------------------------
@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    if request.session.get("is_admin"):
        return RedirectResponse(url="/admin")
    return templates.TemplateResponse(request=request, name="admin_login.html")

@app.post("/admin/login")
async def admin_login_action(request: Request):
    form_data = await request.form()
    username = form_data.get("username")
    password = form_data.get("password")
    
    # Credentials from .env
    env_user = os.getenv("ADMIN_USERNAME", "admin")
    env_pass = os.getenv("ADMIN_PASSWORD", "admin123")
    
    if username == env_user and password == env_pass:
        request.session["is_admin"] = True
        return RedirectResponse(url="/admin", status_code=303)
    
    return templates.TemplateResponse(request=request, name="admin_login.html", context={"error": "Invalid credentials"})

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, _ = Depends(is_admin)):
    df = load_data()
    total_students = len(df) if df is not None else 0
    total_schools = len(df["School Name"].unique()) if df is not None and "School Name" in df.columns else 0
    
    return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={
        "total_students": total_students,
        "total_schools": total_schools
    })

@app.get("/admin/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login")

@app.get("/admin/download-csv")
async def admin_download_csv(_ = Depends(is_admin)):
    if os.path.exists(CSV_DATA_PATH):
        return FileResponse(CSV_DATA_PATH, media_type="text/csv", filename="Student_Data_Backup.csv")
    raise HTTPException(status_code=404, detail="CSV file not found")

@app.post("/admin/upload-csv")
async def admin_upload_csv(request: Request, file: UploadFile = File(...), _ = Depends(is_admin)):
    if not file.filename.endswith(".csv"):
        return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={"error": "Please upload a valid CSV file."})
    
    try:
        # Save to temp file to validate
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        
        # Validate Structure
        try:
            df_new = pd.read_csv(tmp_path)
            required_cols = [
                "Exam Roll Number", "Name", "School Name", "Std.", "Div", "Roll No.", 
                "MCQ TOTAL MARKS", "ESSAY MARKS", "TOTAL",
                "Public Administration", "Business & Startups", "AI & Technology", 
                "Ethical & Moral Values", "International Relation", "Environment & Agriculture", 
                "Culture", "Sports", "Visionary Thinking"
            ]
            missing = [c for c in required_cols if c not in df_new.columns]
            
            if missing:
                os.remove(tmp_path)
                return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={"error": f"Invalid CSV structure. Missing columns: {', '.join(missing)}"})
            
            # Success - Overwrite old file
            df_new.to_csv(CSV_DATA_PATH, index=False)
            os.remove(tmp_path)
            
            # CLEAR CACHE
            _data_cache["df"] = None
            _data_cache["ts"] = 0.0
            
            return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={
                "success": "CSV uploaded and data refreshed successfully!",
                "total_students": len(df_new),
                "total_schools": len(df_new["School Name"].unique()) if "School Name" in df_new.columns else 0
            })
            
        except Exception as e:
            if os.path.exists(tmp_path): os.remove(tmp_path)
            return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={"error": f"Error processing CSV: {str(e)}"})
            
    except Exception as e:
        return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={"error": f"Upload failed: {str(e)}"})

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
    return {"success": True}

@app.post("/api/save-number")
async def api_save_number(body: dict):
    name = body.get("name")
    phone = body.get("phone")
    roll_no = body.get("roll_no")
    school = body.get("school")
    
    if not all([name, phone, roll_no, school]):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    save_collected_number(name, phone, roll_no, school)
    return {"success": True}

@app.get("/admin/collected-numbers")
async def get_collected_numbers(_ = Depends(is_admin)):
    if not os.path.exists(COLLECTED_NUMBERS_PATH):
        return {"rows": []}
    
    try:
        df_leads = pd.read_csv(COLLECTED_NUMBERS_PATH)
        df_leads = df_leads.fillna("")
        return {"rows": df_leads.values.tolist()}
    except Exception as e:
        print(f"Error reading leads: {e}")
        return {"rows": []}

@app.get("/admin/download-leads-csv")
async def download_leads_csv(_ = Depends(is_admin)):
    # If it doesn't exist, create it with headers so the user gets an empty CSV
    if not os.path.exists(COLLECTED_NUMBERS_PATH):
        import csv
        with open(COLLECTED_NUMBERS_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Name", "Phone", "Exam Roll Number", "School"])
            
    return FileResponse(COLLECTED_NUMBERS_PATH, media_type="text/csv", filename="Collected_Numbers.csv")

@app.get("/api/current-student")
async def get_current_student(request: Request):
    idx = request.session.get("student_idx")
    if idx is None:
        raise HTTPException(status_code=401, detail="No student selected")

    # load_data() is now in-memory cached — this is fast after the first call
    df = load_data()
    if df is None: raise HTTPException(status_code=500, detail="Local data could not be loaded")

    row = df.iloc[idx].tolist()
    return {"student": row, "row_index": idx}

# ---------------------------------------------------------------------------
# API: fetch all students from CSV
# ---------------------------------------------------------------------------
@app.get("/api/students")
async def get_students():
    df = load_data()
    if df is None:
        raise HTTPException(status_code=500, detail="CSV data could not be loaded")

    rows = df.values.tolist()
    return {
        "rows": rows
    }

# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# API: PDF Download via Playwright
# ---------------------------------------------------------------------------
@app.get("/api/download-result-pdf")
async def api_download_result_pdf(request: Request):
    idx = request.session.get("student_idx")
    
    if idx is None:
        raise HTTPException(status_code=401, detail="Session expired")

    # 1. Load the student data for rendering
    df = load_data()
    if df is None: raise HTTPException(status_code=500, detail="CSV data could not be loaded")
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
    host = os.environ["HOST"]
    port = int(os.environ["PORT"])
    uvicorn.run("app:app", host=host, port=port, reload=debug_mode)
    