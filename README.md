# Traffic Pulse: Real-Time Network AI & Traffic Operations Center (TOC)

An end-to-end, software-only intelligent transportation system (ITS) that continuously ingests, cleans, analyzes, forecasts, and optimizes traffic conditions across an urban road network using the organizer's 90-day synthetic traffic dataset.

---

## System Architecture

```
traffic_ai_system/
├── .env                              # Environment configuration (Data paths, ports, model thresholds)
├── .env.example                      # Template environment configuration
├── run_system.py                     # Single-command launcher (Starts ASGI server & UI)
├── train_models.py                   # Model training & offline calibration script
├── backend/
│   ├── __init__.py
│   ├── config.py                     # Configuration loader
│   ├── data_loader.py                # Graph topology, detectors, weather, events & corridors
│   ├── pipeline.py                   # Streaming ingestion (Kafka/Flink abstraction), fault cleaning & gap imputation
│   ├── current_state_engine.py       # Macroscopic flow/speed/density, baselines, Isolation Forest anomaly scoring
│   ├── incident_detector.py          # Multi-modal fusion & classifier with low-confidence 'Abnormal Behavior' guardrail
│   ├── forecasting_model.py          # Spatiotemporal Graph Neural Network (ST-GNN) multi-horizon predictions
│   ├── advisory_engine.py            # Dynamic diversion optimization, Webster signal retiming & ramp metering
│   ├── infrastructure_recommender.py # 90-day recurring bottleneck clustering & before/after 24h simulator
│   └── server.py                     # Starlette ASGI server with REST & SSE live streaming endpoints
├── frontend/
│   ├── index.html                    # Single-Page Application (TOC Operations Center UI)
│   ├── css/
│   │   └── styles.css                # Dark operations center theme, responsive layouts & custom widgets
│   └── js/
│       ├── app.js                    # SSE stream receiver, playback controls & tab routing
│       ├── congestion_pulse.js       # View 1: Top 10 Ranked critical bottleneck table
│       ├── corridor_strip.js         # View 2: Space-Time diagram (Haut-Trajectoire shockwave heatmap)
│       ├── incident_panel.js         # View 3: Structured incident cards with triggering signals & evidence
│       ├── advisory_drawer.js        # View 4: Operational advisories with human-in-the-loop Approve/Reject
│       ├── simulator.js              # View 5: Before/After simulator with 24h diurnal replay scrubber
│       └── secondary_map.js          # View 6: Minimalist Leaflet road network map drill-down
├── models/                           # Persisted PyTorch & Scikit-Learn model weights
└── tests/
    └── test_system.py                # Automated end-to-end unit & integration test suite
```

---

## Key Capabilities

### 1. Ingestion & Streaming Hygiene Layer (`backend/pipeline.py`)
- **Streaming Windowing**: Tumbling 300s (5 min) event-time windows with watermarking.
- **Sensor Fault Cleaning**: Detects and rejects `stuck`, `suspect_undercount`, and `missing` detector faults.
- **Multi-Source Imputation**: Fuses floating car probe speeds, network spatial graph interpolation, and weather-adjusted historical diurnal baselines into a unified 105-link time-space grid.

### 2. Current-State & Anomaly Engine (`backend/current_state_engine.py`)
- Computes macroscopic physical state variables: space-mean speed, volume, density (\(k = q / v\)), \(v/c\) ratio, and Highway Capacity Manual Level of Service (LOS A through F).
- Computes speed drop percentage vs. baseline, occupancy spikes, and shockwave gradients.
- Fits an `IsolationForest` model on multivariate telemetry to generate calibrated anomaly scores.
- Ranks links by a composite severity index to drive the **Congestion Pulse** view.

### 3. Incident Detection & Multi-Modal Fusion (`backend/incident_detector.py`)
- Fuses anomaly signals with weather conditions (rainfall, wet friction), active roadworks permits, event schedules, and downstream shockwave gradients.
- Supervised multi-class classification: `Accident / Collision`, `Stalled Vehicle / Breakdown`, `Active Road Work Zone`, and `Road Hazard`.
- **Low-Confidence Guardrail**: When model confidence is below 60%, the event is explicitly labeled **"Abnormal Traffic Behavior"** with attached telemetry evidence to prevent misinforming operators.

### 4. Spatiotemporal ST-GNN Forecasting (`backend/forecasting_model.py`)
- PyTorch Spatio-Temporal Graph Neural Network combining spatial graph convolutions over the 105-link topology with a temporal GRU layer.
- Simultaneously predicts speed and volume across all 105 links for 4 operational horizons: **+15 min, +30 min, +45 min, and +60 min**.

### 5. Operational Advisory Engine (`backend/advisory_engine.py`)
- **Dynamic Diversions**: Runs Dijkstra routing on dynamic travel times to discover alternate corridors, verifies capacity headroom on alternate links (\(v/c < 0.75\)), and quantifies expected delay saved.
- **Webster Signal Re-timing**: Computes optimal green split extensions (+10s to +20s) for approaches entering signalized junctions.
- **Ramp Metering**: Restricts upstream inflow to prevent queue spillback into critical bottlenecks.
- **Human-in-the-Loop**: Interactive **Approve** and **Reject** buttons with persistent operator decision logging.

### 6. Infrastructure Recommender & Before/After Simulator (`backend/infrastructure_recommender.py`)
- Clusters recurring bottlenecks across 90 days of traffic telemetry into 4 engineering typologies (Commuter Chokes, Freeway Merges, Intersection Throats, Lane Drops).
- Proposes actionable engineering options: travel lane additions, turn pockets, adaptive coordinated signal waves, and flyover bypasses.
- Simulates a 24-hour day before vs. after modification using calibrated BPR + queue propagation dynamics.

---

## The 6 Operator UI Views

1. **Congestion Pulse (Home View)**: Ranked list of top 10 critical bottlenecks with severity bars, speed vs baseline %, trend arrows (\(\nearrow \searrow \rightarrow\)), multi-horizon forecast pills, and quick action triggers.
2. **Corridor Timeline Strip (Killer View)**: Space-time diagram (Haut-Trajectoire) rendering space along the corridor (X-axis) against time (Y-axis: past 60m \(\to\) NOW \(\to\) +60m forecast), making shockwave fronts visually obvious.
3. **Incident Evidence Panel**: Structured incident cards with classification badges, triggering signal metrics, interactive speed drop sparklines, simulated CCTV preview, and direct action triggers.
4. **Advisory Drawer**: Actionable operational suggestions with attached evidence ("Divert to Route B – triggered by accident on Link 42, model predicts 22 min saved, confidence 78%"), spare capacity indicators, and Approve/Reject buttons.
5. **Before/After Simulator**: Split view comparing current bottleneck metrics vs. post-modification metrics, with an interactive 24-hour scrub slider (00:00 to 24:00) replaying diurnal traffic evolution.
6. **Network Map Drill-Down**: Minimalist dark road network map with real-time speed/LOS overlay, serving as a secondary drill-down layer when an operator clicks a link.

---

## Quickstart & Verification

### 1. Run Automated Test Suite
```powershell
python tests/test_system.py
```

### 2. Launch the System
```powershell
python run_system.py
```
Open your browser at `http://localhost:8000`.
