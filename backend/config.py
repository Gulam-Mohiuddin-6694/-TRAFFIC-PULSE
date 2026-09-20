"""
Traffic Pulse - System Configuration
Loads configuration from .env and defines runtime parameters.
"""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List


def load_env_file(dotenv_path: Path) -> None:
    """Lightweight .env parser without external dependencies."""
    if not dotenv_path.exists():
        return
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val


# Locate project root and load .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_env_file(PROJECT_ROOT / ".env")


@dataclass
class Config:
    # Directories
    project_root: Path = PROJECT_ROOT
    data_dir: Path = field(default_factory=lambda: Path(os.getenv(
        "DATA_DIR",
        r"C:\Autonomous Traffic Flow Optimization & Road-Safety Response Agents\synthetic_traffic_data\synthetic_traffic_data"
    )))
    models_dir: Path = field(default_factory=lambda: Path(os.getenv("MODELS_DIR", "models")))
    cache_dir: Path = field(default_factory=lambda: Path(os.getenv("CACHE_DIR", "cache")))
    frontend_dir: Path = PROJECT_ROOT / "frontend"

    # Server
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")

    # Traffic Grid & Streaming
    interval_seconds: int = int(os.getenv("INTERVAL_SECONDS", "300"))
    default_start_timestamp: str = os.getenv("DEFAULT_START_TIMESTAMP", "2024-01-01 16:00:00")
    default_stream_speed: float = float(os.getenv("DEFAULT_STREAM_SPEED", "1.0"))

    # AI Detection & Anomaly
    anomaly_speed_drop_threshold: float = float(os.getenv("ANOMALY_SPEED_DROP_THRESHOLD", "0.30"))
    anomaly_occupancy_spike_threshold: float = float(os.getenv("ANOMALY_OCCUPANCY_SPIKE_THRESHOLD", "0.20"))
    incident_confidence_threshold: float = float(os.getenv("INCIDENT_CONFIDENCE_THRESHOLD", "0.60"))
    isolation_forest_contamination: float = float(os.getenv("ISOLATION_FOREST_CONTAMINATION", "0.04"))

    # Forecasting
    forecast_horizons: List[int] = field(default_factory=lambda: [15, 30, 45, 60])
    st_gnn_hidden_dim: int = int(os.getenv("ST_GNN_HIDDEN_DIM", "64"))
    st_gnn_epochs: int = int(os.getenv("ST_GNN_EPOCHS", "15"))

    def __post_init__(self):
        if not self.models_dir.is_absolute():
            self.models_dir = self.project_root / self.models_dir
        if not self.cache_dir.is_absolute():
            self.cache_dir = self.project_root / self.cache_dir
        if not self.data_dir.is_absolute():
            self.data_dir = self.project_root / self.data_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


config = Config()
