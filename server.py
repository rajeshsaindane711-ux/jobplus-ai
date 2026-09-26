"""
JobPlus AI - Local Production Backend Server
Bridges the Web UI with Playwright automation, SQLite database, and real-time logs.
Run: python server.py
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Reconfigure stdout for Windows UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from src.config import CONFIG_DIR, load_profile, load_search_config
from src.database import DatabaseTracker, get_db_tracker
from src.utils.ai_copilot import AICareerCopilot
from src.platforms.job_finder import JobFinderEngine
from src.platforms.form_filler import AutonomousFormFiller

class ApplyJobRequest(BaseModel):
    company: str
    url: str
    title: str = "DevOps Engineer"
    cover_letter: Optional[str] = None
    dry_run: bool = False

class ApplyBatchRequest(BaseModel):
    jobs: Optional[List[Dict[str, Any]]] = None
    dry_run: bool = False

class ResolveReviewRequest(BaseModel):
    review_id: str
    answer: str

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
QA_FILE = DATA_DIR / "learned_qa.json"
HTML_UI_PATH = BASE_DIR / "ui_mockup.html"

from fastapi.staticfiles import StaticFiles

app = FastAPI(title="JobPlus AI Production Server", version="1.0.0")

# Mount static assets
ASSETS_DIR = BASE_DIR / "assets"
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

class ATSScoreRequest(BaseModel):
    resume_text: str
    job_description: str

class CoverLetterRequest(BaseModel):
    candidate_name: str = "Rajesh Saindane"
    position: str = "Senior SRE / DevOps Engineer"
    company: str = "PhonePe"
    experience_years: float = 5.0
    notice_period: str = "30 Days"
    job_description: str = ""

class OutreachRequest(BaseModel):
    candidate_name: str = "Rajesh Saindane"
    recruiter_name: str = "Hiring Manager"
    company: str = "PhonePe"
    position: str = "Senior SRE"

class BulletOptimizeRequest(BaseModel):
    raw_bullet: str
    target_tech: str = "kubernetes"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSocket connections for live logs
class LogConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = LogConnectionManager()

# Models
class QAItem(BaseModel):
    key: str
    value: str

class FilterConfig(BaseModel):
    company_blacklist: List[str]
    keyword_blacklist: List[str]
    min_salary_lpa: float
    max_experience_years: float

# Routes
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serves the main application UI."""
    if not HTML_UI_PATH.exists():
        raise HTTPException(status_code=404, detail="UI file not found")
    return HTMLResponse(content=HTML_UI_PATH.read_text(encoding="utf-8"))

@app.get("/api/status")
async def get_status():
    """Returns local application statistics and platform connection status."""
    try:
        tracker = DatabaseTracker()
        summary = tracker.get_summary_stats()
        naukri_today = tracker.get_today_applied_count("naukri")
        linkedin_today = tracker.get_today_applied_count("linkedin")
        return {
            "status": "online",
            "today": {
                "naukri": naukri_today,
                "linkedin": linkedin_today,
                "total": naukri_today + linkedin_today
            },
            "summary": summary
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/qa")
async def get_qa_bank():
    """Returns the learned screening questions and answers."""
    if QA_FILE.exists():
        try:
            with open(QA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

@app.post("/api/qa")
async def save_qa_item(item: QAItem):
    """Saves or updates a learned question & answer in the local knowledge base."""
    data = {}
    if QA_FILE.exists():
        try:
            with open(QA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    
    data[item.key.strip()] = item.value.strip()
    
    with open(QA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    await manager.broadcast({
        "type": "qa_updated",
        "key": item.key,
        "value": item.value
    })
    return {"status": "success", "count": len(data)}

@app.delete("/api/qa/{key}")
async def delete_qa_item(key: str):
    """Deletes a question & answer from knowledge bank."""
    if not QA_FILE.exists():
        return {"status": "not_found"}
    with open(QA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if key in data:
        del data[key]
        with open(QA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return {"status": "deleted", "key": key}
    return {"status": "not_found"}

@app.get("/api/config")
async def get_config():
    """Returns search criteria and safety guardrails."""
    search_path = CONFIG_DIR / "search_config.yaml"
    if search_path.exists():
        with open(search_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}

@app.post("/api/config/filters")
async def update_filters(filters: FilterConfig):
    """Updates safety guardrails and blacklists."""
    search_path = CONFIG_DIR / "search_config.yaml"
    with open(search_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    
    cfg["filters"] = filters.model_dump()
    
    with open(search_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
        
    return {"status": "updated", "filters": cfg["filters"]}

@app.get("/api/applications")
async def get_applications(limit: int = 50):
    """Returns recent application logs from SQLite database."""
    tracker = DatabaseTracker()
    records = tracker.get_recent_applications(limit=limit)
    return records

# ─────────────────────────────────────────────────────────────────
# AI CAREER COPILOT ROUTES (FREE GEMINI 2.0 FLASH + OFFLINE)
# ─────────────────────────────────────────────────────────────────

@app.post("/api/ai/ats-score")
async def calculate_ats_score(req: ATSScoreRequest):
    """Calculates real-time ATS match percentage and keywords."""
    copilot = AICareerCopilot()
    return copilot.analyze_ats_match(req.resume_text, req.job_description)

@app.post("/api/ai/cover-letter")
async def generate_cover_letter(req: CoverLetterRequest):
    """Generates natural human-written cover letter tailored to role."""
    copilot = AICareerCopilot()
    letter = copilot.generate_cover_letter(
        candidate_name=req.candidate_name,
        position=req.position,
        company=req.company,
        experience_years=req.experience_years,
        notice_period=req.notice_period,
        job_description=req.job_description
    )
    return {"cover_letter": letter}

@app.post("/api/ai/outreach")
async def generate_outreach(req: OutreachRequest):
    """Generates 3-touch recruiter email campaign."""
    copilot = AICareerCopilot()
    return copilot.generate_outreach_sequence(
        candidate_name=req.candidate_name,
        recruiter_name=req.recruiter_name,
        company=req.company,
        position=req.position
    )

@app.post("/api/ai/bullet-optimize")
async def optimize_bullet(req: BulletOptimizeRequest):
    """Rewrites passive bullets into Google X-Y-Z quantified achievements."""
    copilot = AICareerCopilot()
    return copilot.optimize_resume_bullet(req.raw_bullet, req.target_tech)

# ─────────────────────────────────────────────────────────────────
# MULTI-PLATFORM JOB RADAR ROUTES (STEP 3)
# ─────────────────────────────────────────────────────────────────

@app.get("/api/jobs/radar")
async def get_radar_jobs(min_match: float = 85.0, limit: int = 50):
    """Returns queued matched jobs from SQLite database."""
    tracker = DatabaseTracker()
    return tracker.get_matched_jobs(min_match=min_match, limit=limit)

@app.post("/api/jobs/scan")
async def trigger_job_scan():
    """Triggers an on-demand multi-platform scan and stores matches in database."""
    engine = JobFinderEngine()
    results = engine.scan_and_sync_all_platforms()
    await manager.broadcast({
        "type": "log",
        "level": "INFO",
        "message": f"[JOB RADAR] Scan complete: {results['total_discovered']} discovered, {results['total_qualified']} qualified, {results['total_skipped']} filtered out."
    })
    return results

# ─────────────────────────────────────────────────────────────────
# AUTONOMOUS FORM-FILLER & CIRCUIT BREAKER ROUTES (STEP 4)
# ─────────────────────────────────────────────────────────────────

@app.post("/api/apply/job")
async def apply_single_job(req: ApplyJobRequest):
    """Applies to a single job via Autonomous Form-Filler with Circuit Breaker."""
    filler = AutonomousFormFiller()
    await manager.broadcast({
        "type": "log",
        "level": "INFO",
        "message": f"[AUTO APPLY] Starting submission for {req.company} - {req.title} (DryRun: {req.dry_run})"
    })
    result = filler.fill_and_submit_direct_ats(
        company=req.company,
        job_url=req.url,
        role=req.title,
        cover_letter=req.cover_letter,
        dry_run=req.dry_run
    )
    status_label = result.get("status", "unknown").upper()
    await manager.broadcast({
        "type": "log",
        "level": "INFO" if status_label in ["APPLIED", "DRY_RUN_SUCCESS", "SIMULATED"] else "WARNING",
        "message": f"[AUTO APPLY] {req.company} -> {status_label}"
    })
    return result

@app.post("/api/apply/batch")
async def apply_batch_jobs(req: ApplyBatchRequest):
    """Executes 1-Click Autonomous Batch Application across matched jobs."""
    filler = AutonomousFormFiller()
    tracker = DatabaseTracker()

    jobs_to_apply = req.jobs
    if not jobs_to_apply:
        # Pull top matched jobs from radar
        jobs_to_apply = tracker.get_matched_jobs(min_match=85.0, limit=20)

    await manager.broadcast({
        "type": "log",
        "level": "INFO",
        "message": f"[1-CLICK BATCH] Starting automated batch application for {len(jobs_to_apply)} jobs..."
    })

    result = filler.process_batch(jobs_to_apply, dry_run=req.dry_run)

    await manager.broadcast({
        "type": "log",
        "level": "INFO",
        "message": f"[1-CLICK BATCH] Batch complete: Applied={result['applied']}, Skipped={result['skipped']}, CircuitBreaks={result['circuit_broken']}"
    })
    return result

@app.post("/api/apply/live-demo")
async def launch_live_browser_demo():
    """Launches a real visible Chrome/Chromium window on your desktop to demonstrate live form-filling."""
    from scripts.test_live_browser import run_live_browser_demo
    await manager.broadcast({
        "type": "log",
        "level": "INFO",
        "message": "[LIVE DEMO] 🚀 Launching real visible Chromium window on your desktop screen..."
    })
    try:
        run_live_browser_demo()
        await manager.broadcast({
            "type": "log",
            "level": "INFO",
            "message": "[LIVE DEMO] ✓ Live form filling demonstration completed successfully!"
        })
        return {"status": "success", "message": "Live browser demonstration completed."}
    except Exception as e:
        await manager.broadcast({
            "type": "log",
            "level": "ERROR",
            "message": f"[LIVE DEMO] Error: {str(e)}"
        })
        return {"status": "error", "message": str(e)}

@app.get("/api/apply/review-queue")
async def get_review_queue():
    """Returns all questions pending human verification."""
    filler = AutonomousFormFiller()
    queue = filler.verifier.review_queue
    pending = [item for item in queue if item.get("status") == "PENDING_USER_INPUT"]
    return {"pending_count": len(pending), "items": pending}

@app.post("/api/apply/review-queue/resolve")
async def resolve_review_question(req: ResolveReviewRequest):
    """Resolves an enqueued question, updates QA memory bank, and allows auto-resume."""
    filler = AutonomousFormFiller()
    success = filler.resolve_review_item(req.review_id, req.answer)
    await manager.broadcast({
        "type": "log",
        "level": "INFO",
        "message": f"[KNOWLEDGE BASE] Learned answer for '{req.review_id}' -> '{req.answer}'"
    })
    return {"success": success, "review_id": req.review_id, "answer": req.answer}

@app.get("/api/qa/all")
async def get_all_qa():
    """Returns all stored questions and answers from knowledge bank."""
    tracker = DatabaseTracker()
    return tracker.get_all_qa_items()

@app.get("/api/applications/recent")
async def get_recent_applications(limit: int = 50):
    """Returns recent applications with status, platform, and timestamps."""
    tracker = DatabaseTracker()
    return tracker.get_recent_applications(limit=limit)


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket stream for real-time Playwright automation logs."""
    await manager.connect(websocket)
    try:
        # Welcome message
        await websocket.send_json({
            "type": "log",
            "level": "INFO",
            "message": "Connected to JobPlus AI Production Engine (Playwright v1.63.0 ready)."
        })
        while True:
            data = await websocket.receive_text()
            # Handle client commands like ping or trigger
            msg = json.loads(data)
            if msg.get("action") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("      JOBPLUS AI - LOCAL PRODUCTION SERVER")
    print("      Listening on: http://127.0.0.1:8000")
    print("="*50 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
