"""
Traffic Pulse - Starlette ASGI Server & REST/SSE Endpoints
Provides real-time API for Congestion Pulse, Space-Time corridor diagrams,
Incident evidence panels, Advisory drawer, Infrastructure simulator, and Secondary Map.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

import numpy as np
import pandas as pd
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from backend.config import config
from backend.data_loader import data_loader
from backend.pipeline import pipeline
from backend.current_state_engine import current_state_engine
from backend.incident_detector import incident_detector
from backend.forecasting_model import forecaster
from backend.advisory_engine import advisory_engine
from backend.infrastructure_recommender import infrastructure_recommender


class StreamingState:
    """Manages playback clock and live streaming state."""
    def __init__(self):
        self.current_time: pd.Timestamp = pd.Timestamp(config.default_start_timestamp)
        self.is_playing: bool = False
        self.playback_speed: float = config.default_stream_speed
        self.step_seconds: int = config.interval_seconds  # 300s = 5 min
        self.history_buffer: List[Dict[str, Any]] = []

    def tick(self) -> pd.Timestamp:
        self.current_time += timedelta(seconds=self.step_seconds)
        return self.current_time

    def set_time(self, ts: str) -> pd.Timestamp:
        self.current_time = pd.Timestamp(ts)
        return self.current_time


stream_state = StreamingState()


# ==============================================================================
# API Endpoints
# ==============================================================================

async def get_network(request: Request) -> JSONResponse:
    """Returns static network graph, corridors, and GeoJSON features."""
    corridors_summary = [
        {
            "id": cid,
            "label": cdata["label"],
            "total_length_m": cdata["total_length_m"],
            "links_count": len(cdata["links"])
        }
        for cid, cdata in data_loader.corridors.items()
    ]
    return JSONResponse({
        "nodes_count": len(data_loader.node_map),
        "links_count": len(data_loader.link_map),
        "detectors_count": len(data_loader.detectors_df),
        "corridors": corridors_summary,
        "geojson": data_loader.network_geojson
    })


async def get_current_state(request: Request) -> JSONResponse:
    """Computes and returns full current state for stream_state.current_time."""
    dt = stream_state.current_time

    # 1. Pipeline ingestion and cleaning
    df_window = pipeline.ingest_window(dt)

    # 2. ST-GNN multi-horizon forecasting (+15, +30, +45, +60m)
    forecasts = forecaster.predict(df_window.to_dict("records"), dt=dt)

    # 3. Current-state engine & Congestion Pulse ranking
    state_out = current_state_engine.compute_current_state(df_window, forecasts=forecasts)

    # 4. Incident detection with multi-modal fusion & low-conf abnormal behavior guardrail
    incidents = incident_detector.detect_incidents(state_out["all_links"], dt)

    # 5. Advisory engine recommendations
    advisories = advisory_engine.generate_advisories(state_out["all_links"], incidents, dt)

    return JSONResponse({
        "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "is_playing": stream_state.is_playing,
        "playback_speed": stream_state.playback_speed,
        "network_summary": state_out["network_summary"],
        "congestion_pulse_top10": state_out["congestion_pulse_top10"],
        "active_incidents": incidents,
        "active_advisories": advisories,
        "all_links": state_out["all_links"]
    })


async def get_corridor_timeline(request: Request) -> JSONResponse:
    """
    Computes the Space-Time Diagram (Haut-Trajectoire) for the selected corridor.
    X-axis: Distance along corridor (meters)
    Y-axis: Time (Last 60m -> NOW -> +60m Forecast)
    """
    cid = request.query_params.get("corridor", "EW-TRU-EB")
    corridor_data = data_loader.corridors.get(cid)
    if not corridor_data:
        cid = list(data_loader.corridors.keys())[0]
        corridor_data = data_loader.corridors[cid]

    now_dt = stream_state.current_time
    corridor_links = corridor_data["links"]

    time_rows = []

    # 1. Past 60 minutes history (12 intervals of 5 minutes: -55m .. -5m)
    for step in range(11, -1, -1):
        hist_dt = now_dt - timedelta(minutes=step * 5)
        df_hist = pipeline.ingest_window(hist_dt)
        hist_map = df_hist.set_index("link_id")

        cells = []
        for linfo in corridor_links:
            lid = linfo["link_id"]
            if lid in hist_map.index:
                row = hist_map.loc[lid]
                spd = float(row["speed_kph"])
                occ = float(row["occupancy_pct"])
                los = str(row["level_of_service"])
            else:
                spd = float(linfo["free_flow_speed_kph"])
                occ = 10.0
                los = "A"

            ff = float(linfo["free_flow_speed_kph"])
            ratio = spd / ff if ff > 0 else 1.0

            cells.append({
                "link_id": lid,
                "name": linfo["name"],
                "start_m": linfo["start_m"],
                "end_m": linfo["end_m"],
                "speed_kph": round(spd, 1),
                "speed_ratio": round(ratio, 2),
                "occupancy_pct": round(occ, 1),
                "los": los
            })

        time_rows.append({
            "time_str": hist_dt.strftime("%H:%M"),
            "timestamp": hist_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "offset_min": -step * 5,
            "is_now": (step == 0),
            "is_forecast": False,
            "cells": cells
        })

    # 2. Future 60 minutes forecast (+15m, +30m, +45m, +60m)
    df_current = pipeline.ingest_window(now_dt)
    forecasts = forecaster.predict(df_current.to_dict("records"), dt=now_dt)

    for h_name, offset in [("+15m", 15), ("+30m", 30), ("+45m", 45), ("+60m", 60)]:
        f_dt = now_dt + timedelta(minutes=offset)
        cells = []
        for linfo in corridor_links:
            lid = linfo["link_id"]
            fc = forecasts.get(lid, {})
            spd = float(fc.get(h_name, linfo["free_flow_speed_kph"] * 0.9))
            ff = float(linfo["free_flow_speed_kph"])
            ratio = spd / ff if ff > 0 else 1.0
            los = "A" if ratio >= 0.85 else ("B" if ratio >= 0.70 else ("C" if ratio >= 0.55 else ("D" if ratio >= 0.40 else "F")))

            cells.append({
                "link_id": lid,
                "name": linfo["name"],
                "start_m": linfo["start_m"],
                "end_m": linfo["end_m"],
                "speed_kph": round(spd, 1),
                "speed_ratio": round(ratio, 2),
                "occupancy_pct": 20.0,
                "los": los
            })

        time_rows.append({
            "time_str": f"{f_dt.strftime('%H:%M')} ({h_name})",
            "timestamp": f_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "offset_min": offset,
            "is_now": False,
            "is_forecast": True,
            "cells": cells
        })

    return JSONResponse({
        "corridor_id": cid,
        "label": corridor_data["label"],
        "total_length_m": corridor_data["total_length_m"],
        "links": corridor_links,
        "timeline_rows": time_rows
    })


async def get_incidents(request: Request) -> JSONResponse:
    """Returns detected incidents with complete evidence packages."""
    dt = stream_state.current_time
    df_window = pipeline.ingest_window(dt)
    state_out = current_state_engine.compute_current_state(df_window)
    incidents = incident_detector.detect_incidents(state_out["all_links"], dt)
    return JSONResponse({
        "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "incidents": incidents
    })


async def post_advisory_action(request: Request) -> JSONResponse:
    """Human-in-the-loop action on an advisory card (APPROVE / REJECT)."""
    adv_id = request.path_params["advisory_id"]
    body = await request.json()
    action = body.get("action", "APPROVE")
    notes = body.get("notes", "Operator confirmed via dashboard")
    rec = advisory_engine.record_decision(adv_id, action, notes)
    return JSONResponse({"status": "success", "record": rec})


async def get_infrastructure_bottlenecks(request: Request) -> JSONResponse:
    """Returns recurring bottleneck clusters and proposed engineering modifications."""
    return JSONResponse({
        "clusters": infrastructure_recommender.bottleneck_clusters,
        "projects": list(infrastructure_recommender.projects.values())
    })


async def get_infrastructure_simulate(request: Request) -> JSONResponse:
    """Runs before/after 24-hour simulation for a selected project."""
    project_id = request.query_params.get("project_id", "PROJ-LANE-EW-TRU")
    sim_result = infrastructure_recommender.simulate_project_impact(project_id)
    return JSONResponse(sim_result)


async def post_playback(request: Request) -> JSONResponse:
    """Controls simulation playback: play, pause, step, speed, jump."""
    body = await request.json()
    action = body.get("action")

    if action == "play":
        stream_state.is_playing = True
    elif action == "pause":
        stream_state.is_playing = False
    elif action == "step":
        stream_state.tick()
    elif action == "speed":
        stream_state.playback_speed = float(body.get("speed", 1.0))
    elif action == "jump":
        target = body.get("timestamp")
        if target:
            stream_state.set_time(target)

    return JSONResponse({
        "timestamp": stream_state.current_time.strftime("%Y-%m-%d %H:%M:%S"),
        "is_playing": stream_state.is_playing,
        "playback_speed": stream_state.playback_speed
    })


async def sse_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events (SSE) live feed pushing state ticks to the browser."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break

            if stream_state.is_playing:
                stream_state.tick()

            dt = stream_state.current_time
            try:
                df_window = pipeline.ingest_window(dt)
                state_out = current_state_engine.compute_current_state(df_window)
                incidents = incident_detector.detect_incidents(state_out["all_links"], dt)
                advisories = advisory_engine.generate_advisories(state_out["all_links"], incidents, dt)

                payload = {
                    "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "is_playing": stream_state.is_playing,
                    "network_summary": state_out["network_summary"],
                    "congestion_pulse_top10": state_out["congestion_pulse_top10"],
                    "active_incidents": incidents,
                    "active_advisories": advisories
                }
                yield f"data: {json.dumps(payload)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

            # Sleep interval inversely proportional to playback speed
            delay = max(0.5, 3.0 / max(0.2, stream_state.playback_speed))
            await asyncio.sleep(delay)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


# ==============================================================================
# Application Factory
# ==============================================================================

routes = [
    Route("/api/network", get_network, methods=["GET"]),
    Route("/api/current_state", get_current_state, methods=["GET"]),
    Route("/api/corridor_timeline", get_corridor_timeline, methods=["GET"]),
    Route("/api/incidents", get_incidents, methods=["GET"]),
    Route("/api/advisory/{advisory_id}/action", post_advisory_action, methods=["POST"]),
    Route("/api/infrastructure/bottlenecks", get_infrastructure_bottlenecks, methods=["GET"]),
    Route("/api/infrastructure/simulate", get_infrastructure_simulate, methods=["GET"]),
    Route("/api/playback", post_playback, methods=["POST"]),
    Route("/api/stream", sse_stream, methods=["GET"]),
]

# Mount frontend static files
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    routes.append(Mount("/", app=StaticFiles(directory=str(frontend_dir), html=True), name="static"))

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"]
    )
]

app = Starlette(routes=routes, middleware=middleware, debug=config.debug)
