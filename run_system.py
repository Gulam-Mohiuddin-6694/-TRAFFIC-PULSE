#!/usr/bin/env python3
"""
Traffic Pulse - System Launcher
Starts the Uvicorn ASGI backend server serving both REST/SSE APIs and the Operations UI.
"""

import sys
import uvicorn
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import config


def main():
    print("=" * 70)
    print(" TRAFFIC PULSE: REAL-TIME NETWORK AI & OPERATIONS CENTER (TOC)")
    print("=" * 70)
    print(f" Data Directory    : {config.data_dir}")
    print(f" Models Directory  : {config.models_dir}")
    print(f" Server Host/Port  : http://{config.host}:{config.port}")
    print(f" Initial Timestamp : {config.default_start_timestamp}")
    print("=" * 70)
    print("\nStarting Uvicorn ASGI Server...")
    print(f"Open your browser at: http://localhost:{config.port}\n")

    uvicorn.run(
        "backend.server:app",
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
