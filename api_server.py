"""
api_server.py - FastAPI Backend for Fatigue Analysis Tool
==========================================================

RESTful API exposing your Python fatigue model to frontend.

Endpoints:
- POST /api/analyze - Upload roster, get analysis
- GET /api/analysis/{id} - Get stored analysis
- POST /api/visualize/chronogram - Generate chronogram image
- POST /api/visualize/calendar - Generate aviation calendar

Usage:
    uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
import tempfile
import os
from datetime import datetime
import base64
from pathlib import Path

# Import your fatigue model
from core_model import BorbelyFatigueModel
from roster_parser import PDFRosterParser, CSVRosterParser
from config import ModelConfig
from data_models import MonthlyAnalysis, DutyTimeline
from chronogram import FatigueChronogram
from aviation_calendar import AviationCalendar
from visualization import FatigueVisualizer

# ============================================================================
# FASTAPI APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="Fatigue Analysis API",
    description="EASA-compliant biomathematical fatigue analysis",
    version="4.0.0"
)

# CORS - Allow Lovable frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "https://*.lovable.app",
        "https://*.lovable.dev",
        "https://fatigue-insight-hub.lovable.app",
        "*"  # For development - restrict in production!
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class AnalysisRequest(BaseModel):
    pilot_id: str
    month: str  # Format: "2026-02"
    home_base: str  # Airport code (e.g., "DOH")
    home_timezone: str  # e.g., "Asia/Qatar"
    config_preset: str = "default"  # "default", "conservative", "liberal", "research"


class DutySegmentResponse(BaseModel):
    flight_number: str
    departure: str
    arrival: str
    departure_time: str  # UTC ISO format
    arrival_time: str    # UTC ISO format
    departure_time_local: str  # Home base local time in HH:mm format
    arrival_time_local: str    # Home base local time in HH:mm format
    block_hours: float


class SleepBlockResponse(BaseModel):
    """Individual sleep period with timing"""
    sleep_start_time: str  # HH:mm in home-base timezone
    sleep_end_time: str    # HH:mm in home-base timezone
    sleep_type: str        # 'main', 'nap', 'anchor'
    duration_hours: float
    effective_hours: float
    quality_factor: float


class SleepQualityResponse(BaseModel):
    """Sleep quality analysis from enhanced strategic estimator"""
    total_sleep_hours: float
    effective_sleep_hours: float
    sleep_efficiency: float
    wocl_overlap_hours: float
    sleep_strategy: str  # 'normal', 'afternoon_nap', 'early_bedtime', 'split_sleep'
    confidence: float
    warnings: List[str]
    sleep_blocks: List[SleepBlockResponse] = []  # All sleep periods
    sleep_start_time: Optional[str] = None  # Primary sleep start (HH:mm)
    sleep_end_time: Optional[str] = None    # Primary sleep end (HH:mm)


class DutyResponse(BaseModel):
    duty_id: str
    date: str
    report_time_utc: str
    release_time_utc: str
    duty_hours: float
    sectors: int
    segments: List[DutySegmentResponse]
    
    # Performance metrics
    min_performance: float
    avg_performance: float
    landing_performance: Optional[float]
    
    # Fatigue metrics
    sleep_debt: float
    wocl_hours: float
    prior_sleep: float
    
    # Risk
    risk_level: str  # "low", "moderate", "high", "critical", "extreme"
    is_reportable: bool
    pinch_events: int
    
    # EASA FDP limits
    max_fdp_hours: Optional[float]  # Base FDP limit
    extended_fdp_hours: Optional[float]  # With captain discretion
    used_discretion: bool  # True if exceeded base limit
    
    # Enhanced sleep quality analysis
    sleep_quality: Optional[SleepQualityResponse] = None


class AnalysisResponse(BaseModel):
    analysis_id: str
    roster_id: str
    pilot_id: str
    pilot_name: Optional[str]  # Extracted from PDF
    pilot_base: Optional[str]  # Home base airport
    pilot_aircraft: Optional[str]  # Aircraft type
    month: str
    
    # Summary
    total_duties: int
    total_sectors: int
    total_duty_hours: float
    total_block_hours: float
    
    # Risk summary
    high_risk_duties: int
    critical_risk_duties: int
    total_pinch_events: int
    
    # Sleep metrics
    avg_sleep_per_night: float
    max_sleep_debt: float
    
    # Worst case
    worst_duty_id: str
    worst_performance: float
    
    # Detailed duties
    duties: List[DutyResponse]


class ChronogramRequest(BaseModel):
    analysis_id: str
    mode: str = "risk"  # "risk", "state", "hybrid"
    theme: str = "light"
    show_annotations: bool = True


class CalendarRequest(BaseModel):
    analysis_id: str
    theme: str = "light"


# ============================================================================
# IN-MEMORY STORAGE (Replace with database in production)
# ============================================================================

analysis_store = {}  # analysis_id -> (MonthlyAnalysis, Roster)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def classify_risk(performance: Optional[float]) -> str:
    """Classify risk level based on performance score"""
    if performance is None:
        return "unknown"
    if performance >= 75:
        return "low"
    elif performance >= 65:
        return "moderate"
    elif performance >= 55:
        return "high"
    elif performance >= 45:
        return "critical"
    else:
        return "extreme"


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "ok",
        "service": "Fatigue Analysis API",
        "version": "4.0.0",
        "model": "Borbély Two-Process + Workload Integration"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_roster(
    file: UploadFile = File(...),
    pilot_id: str = Form("P12345"),
    month: str = Form("2026-02"),
    home_base: str = Form("DOH"),
    home_timezone: str = Form("Asia/Qatar"),
    config_preset: str = Form("default")
):
    """
    Upload roster file and get fatigue analysis
    
    Returns complete analysis with duty-by-duty breakdown
    """
    
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Save uploaded file
        suffix = Path(file.filename).suffix.lower()
        if suffix not in ['.pdf', '.csv']:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use PDF or CSV.")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # Parse roster
            if suffix == '.pdf':
                parser = PDFRosterParser(
                    home_base=home_base,
                    home_timezone=home_timezone
                )
                roster = parser.parse_pdf(tmp_path, pilot_id, month)
            else:  # CSV
                parser = CSVRosterParser(
                    home_base=home_base,
                    home_timezone=home_timezone
                )
                roster = parser.parse_csv(tmp_path, pilot_id, month)
        finally:
            # Clean up temp file
            os.unlink(tmp_path)
        
        # Validate roster
        if not roster.duties:
            raise HTTPException(status_code=400, detail="No duties found in roster")
        
        # Get config
        config_map = {
            "default": ModelConfig.default_easa_config,
            "conservative": ModelConfig.conservative_config,
            "liberal": ModelConfig.liberal_config,
            "research": ModelConfig.research_config
        }
        config_func = config_map.get(config_preset, ModelConfig.default_easa_config)
        config = config_func()
        
        # Run analysis
        model = BorbelyFatigueModel(config)
        monthly_analysis = model.simulate_roster(roster)
        
        # Generate analysis ID
        analysis_id = f"{pilot_id}_{month}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Store for later retrieval
        analysis_store[analysis_id] = (monthly_analysis, roster)
        
        # Build response
        duties_response = []
        
        for duty_timeline in monthly_analysis.duty_timelines:
            duty_idx = roster.get_duty_index(duty_timeline.duty_id)
            if duty_idx is None:
                continue
            duty = roster.duties[duty_idx]
            
            # Classify risk
            risk = classify_risk(duty_timeline.landing_performance)
            
            # Get home base timezone for local time conversion
            import pytz
            home_tz = pytz.timezone(duty.home_base_timezone)
            
            # Build segments
            segments = []
            for seg in duty.segments:
                # Convert UTC times to home base local time
                dep_utc = seg.scheduled_departure_utc
                arr_utc = seg.scheduled_arrival_utc
                dep_local = dep_utc.astimezone(home_tz)
                arr_local = arr_utc.astimezone(home_tz)
                
                segments.append(DutySegmentResponse(
                    flight_number=seg.flight_number,
                    departure=seg.departure_airport.code,
                    arrival=seg.arrival_airport.code,
                    departure_time=dep_utc.isoformat(),
                    arrival_time=arr_utc.isoformat(),
                    departure_time_local=dep_local.strftime("%H:%M"),
                    arrival_time_local=arr_local.strftime("%H:%M"),
                    block_hours=seg.block_time_hours
                ))
            
            duties_response.append(DutyResponse(
                duty_id=duty_timeline.duty_id,
                date=duty_timeline.duty_date.strftime("%Y-%m-%d"),
                report_time_utc=duty.report_time_utc.isoformat(),
                release_time_utc=duty.release_time_utc.isoformat(),
                duty_hours=duty.duty_hours,
                sectors=len(duty.segments),
                segments=segments,
                min_performance=duty_timeline.min_performance,
                avg_performance=duty_timeline.average_performance,
                landing_performance=duty_timeline.landing_performance,
                sleep_debt=duty_timeline.cumulative_sleep_debt,
                wocl_hours=duty_timeline.wocl_encroachment_hours,
                prior_sleep=duty_timeline.prior_sleep_hours,
                risk_level=risk,
                is_reportable=(risk in ["critical", "extreme"]),
                pinch_events=len(duty_timeline.pinch_events),
                max_fdp_hours=duty.max_fdp_hours,
                extended_fdp_hours=duty.extended_fdp_hours,
                used_discretion=duty.used_discretion,
                sleep_quality=SleepQualityResponse(
                    total_sleep_hours=duty_timeline.sleep_quality_data.get('total_sleep_hours', 0.0),
                    effective_sleep_hours=duty_timeline.sleep_quality_data.get('effective_sleep_hours', 0.0),
                    sleep_efficiency=duty_timeline.sleep_quality_data.get('sleep_efficiency', 0.0),
                    wocl_overlap_hours=duty_timeline.sleep_quality_data.get('wocl_overlap_hours', 0.0),
                    sleep_strategy=duty_timeline.sleep_quality_data.get('strategy_type', 'unknown'),
                    confidence=duty_timeline.sleep_quality_data.get('confidence', 0.0),
                    warnings=duty_timeline.sleep_quality_data.get('warnings', []),
                    sleep_blocks=duty_timeline.sleep_quality_data.get('sleep_blocks', []),
                    sleep_start_time=duty_timeline.sleep_quality_data.get('sleep_start_time'),
                    sleep_end_time=duty_timeline.sleep_quality_data.get('sleep_end_time')
                ) if duty_timeline.sleep_quality_data else None
            ))
        
        return AnalysisResponse(
            analysis_id=analysis_id,
            roster_id=roster.roster_id,
            pilot_id=roster.pilot_id,            pilot_name=roster.pilot_name,
            pilot_base=roster.pilot_base,
            pilot_aircraft=roster.pilot_aircraft,            month=roster.month,
            total_duties=roster.total_duties,
            total_sectors=roster.total_sectors,
            total_duty_hours=roster.total_duty_hours,
            total_block_hours=roster.total_block_hours,
            high_risk_duties=monthly_analysis.high_risk_duties,
            critical_risk_duties=monthly_analysis.critical_risk_duties,
            total_pinch_events=monthly_analysis.total_pinch_events,
            avg_sleep_per_night=monthly_analysis.average_sleep_per_night,
            max_sleep_debt=monthly_analysis.max_sleep_debt,
            worst_duty_id=monthly_analysis.lowest_performance_duty,
            worst_performance=monthly_analysis.lowest_performance_value,
            duties=duties_response
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.get("/api/analysis/{analysis_id}")
async def get_analysis(analysis_id: str):
    """Retrieve stored analysis by ID"""
    
    if analysis_id not in analysis_store:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    monthly_analysis, roster = analysis_store[analysis_id]
    
    # Build duties response
    duties_response = []
    for duty_timeline in monthly_analysis.duty_timelines:
        duty_idx = roster.get_duty_index(duty_timeline.duty_id)
        if duty_idx is None:
            continue
        duty = roster.duties[duty_idx]
        risk = classify_risk(duty_timeline.landing_performance)
        
        # Get home base timezone for local time conversion
        import pytz
        home_tz = pytz.timezone(duty.home_base_timezone)
        
        segments = []
        for seg in duty.segments:
            # Convert UTC times to home base local time
            dep_utc = seg.scheduled_departure_utc
            arr_utc = seg.scheduled_arrival_utc
            dep_local = dep_utc.astimezone(home_tz)
            arr_local = arr_utc.astimezone(home_tz)
            
            segments.append({
                "flight_number": seg.flight_number,
                "departure": seg.departure_airport.code,
                "arrival": seg.arrival_airport.code,
                "departure_time": dep_utc.isoformat(),
                "arrival_time": arr_utc.isoformat(),
                "departure_time_local": dep_local.strftime("%H:%M"),
                "arrival_time_local": arr_local.strftime("%H:%M"),
                "block_hours": seg.block_time_hours
            })
        
        duties_response.append({
            "duty_id": duty_timeline.duty_id,
            "date": duty_timeline.duty_date.strftime("%Y-%m-%d"),
            "report_time_utc": duty.report_time_utc.isoformat(),
            "release_time_utc": duty.release_time_utc.isoformat(),
            "duty_hours": duty.duty_hours,
            "sectors": len(duty.segments),
            "segments": segments,
            "min_performance": duty_timeline.min_performance,
            "avg_performance": duty_timeline.average_performance,
            "landing_performance": duty_timeline.landing_performance,
            "sleep_debt": duty_timeline.cumulative_sleep_debt,
            "wocl_hours": duty_timeline.wocl_encroachment_hours,
            "prior_sleep": duty_timeline.prior_sleep_hours,
            "risk_level": risk,
            "is_reportable": risk in ["critical", "extreme"],
            "pinch_events": len(duty_timeline.pinch_events)
        })
    
    return {
        "analysis_id": analysis_id,
        "roster_id": roster.roster_id,
        "pilot_id": roster.pilot_id,
        "month": roster.month,
        "total_duties": roster.total_duties,
        "total_sectors": roster.total_sectors,
        "total_duty_hours": roster.total_duty_hours,
        "total_block_hours": roster.total_block_hours,
        "high_risk_duties": monthly_analysis.high_risk_duties,
        "critical_risk_duties": monthly_analysis.critical_risk_duties,
        "total_pinch_events": monthly_analysis.total_pinch_events,
        "avg_sleep_per_night": monthly_analysis.average_sleep_per_night,
        "max_sleep_debt": monthly_analysis.max_sleep_debt,
        "worst_duty_id": monthly_analysis.lowest_performance_duty,
        "worst_performance": monthly_analysis.lowest_performance_value,
        "duties": duties_response
    }


@app.post("/api/visualize/chronogram")
async def generate_chronogram(request: ChronogramRequest):
    """
    Generate high-resolution chronogram image
    Returns base64-encoded PNG
    """
    
    if request.analysis_id not in analysis_store:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    monthly_analysis, roster = analysis_store[request.analysis_id]
    
    try:
        chrono = FatigueChronogram(theme=request.theme)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            chrono.plot_monthly_chronogram(
                monthly_analysis,
                save_path=tmp.name,
                mode=request.mode,
                show_annotations=request.show_annotations
            )
            
            # Read and encode as base64
            with open(tmp.name, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode()
            
            os.unlink(tmp.name)
        
        return {
            "image": f"data:image/png;base64,{image_data}",
            "format": "png"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chronogram generation failed: {str(e)}")


@app.post("/api/visualize/calendar")
async def generate_calendar(request: CalendarRequest):
    """Generate aviation calendar image"""
    
    if request.analysis_id not in analysis_store:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    monthly_analysis, roster = analysis_store[request.analysis_id]
    
    try:
        cal = AviationCalendar(theme=request.theme)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            cal.plot_monthly_roster(monthly_analysis, save_path=tmp.name)
            
            with open(tmp.name, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode()
            
            os.unlink(tmp.name)
        
        return {
            "image": f"data:image/png;base64,{image_data}",
            "format": "png"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calendar generation failed: {str(e)}")


@app.get("/api/duty/{analysis_id}/{duty_id}")
async def get_duty_detail(analysis_id: str, duty_id: str):
    """
    Get detailed timeline data for a single duty
    Returns all performance points for interactive charting
    """
    
    if analysis_id not in analysis_store:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    monthly_analysis, roster = analysis_store[analysis_id]
    
    # Find duty
    duty_timeline = None
    for dt in monthly_analysis.duty_timelines:
        if dt.duty_id == duty_id:
            duty_timeline = dt
            break
    
    if not duty_timeline:
        raise HTTPException(status_code=404, detail="Duty not found")
    
    # Build timeline data for frontend charting
    timeline_data = []
    
    for point in duty_timeline.timeline:
        timeline_data.append({
            "timestamp": point.timestamp_utc.isoformat(),
            "timestamp_local": point.timestamp_local.isoformat(),
            "performance": point.raw_performance,
            "sleep_pressure": point.homeostatic_component,
            "circadian": point.circadian_component,
            "flight_phase": point.current_flight_phase.value if point.current_flight_phase else None,
            "is_critical": point.is_critical_phase
        })
    
    return {
        "duty_id": duty_id,
        "timeline": timeline_data,
        "summary": {
            "min_performance": duty_timeline.min_performance,
            "avg_performance": duty_timeline.average_performance,
            "landing_performance": duty_timeline.landing_performance,
            "wocl_hours": duty_timeline.wocl_encroachment_hours,
            "prior_sleep": duty_timeline.prior_sleep_hours,
            "sleep_debt": duty_timeline.cumulative_sleep_debt
        },
        "pinch_events": [
            {
                "timestamp": pe.timestamp_utc.isoformat(),
                "performance": pe.performance_value,
                "phase": pe.flight_phase.value if pe.flight_phase else None,
                "cause": pe.cause
            }
            for pe in duty_timeline.pinch_events
        ]
    }


@app.get("/api/statistics/{analysis_id}")
async def get_statistics(analysis_id: str):
    """Get summary statistics for frontend dashboard"""
    
    if analysis_id not in analysis_store:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    monthly_analysis, roster = analysis_store[analysis_id]
    
    # Calculate additional statistics
    all_perfs = [dt.landing_performance for dt in monthly_analysis.duty_timelines 
                 if dt.landing_performance is not None]
    
    return {
        "analysis_id": analysis_id,
        "summary": {
            "total_duties": roster.total_duties,
            "total_sectors": roster.total_sectors,
            "total_duty_hours": roster.total_duty_hours,
            "total_block_hours": roster.total_block_hours,
        },
        "risk": {
            "high_risk_duties": monthly_analysis.high_risk_duties,
            "critical_risk_duties": monthly_analysis.critical_risk_duties,
            "total_pinch_events": monthly_analysis.total_pinch_events,
        },
        "performance": {
            "average_landing_performance": sum(all_perfs) / len(all_perfs) if all_perfs else None,
            "min_landing_performance": min(all_perfs) if all_perfs else None,
            "max_landing_performance": max(all_perfs) if all_perfs else None,
            "worst_duty_id": monthly_analysis.lowest_performance_duty,
            "worst_performance": monthly_analysis.lowest_performance_value,
        },
        "sleep": {
            "avg_sleep_per_night": monthly_analysis.average_sleep_per_night,
            "max_sleep_debt": monthly_analysis.max_sleep_debt,
        }
    }


# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 70)
    print("FATIGUE ANALYSIS API SERVER")
    print("=" * 70)
    print()
    print("Starting FastAPI server...")
    print("API will be available at: http://localhost:8000")
    print("API docs at: http://localhost:8000/docs")
    print()
    print("Frontend can now connect to:")
    print("  POST http://localhost:8000/api/analyze")
    print("  POST http://localhost:8000/api/visualize/chronogram")
    print("  GET  http://localhost:8000/api/duty/{analysis_id}/{duty_id}")
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
