"""
Traffic Pulse - Current-State Engine & Anomaly Detector
Computes live macroscopic state, speed drops vs baseline, occupancy spikes,
stop-and-go patterns, and Isolation Forest anomaly scores.
Produces the ranked Top-10 Bottleneck Pulse list.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from backend.config import config
from backend.data_loader import DataLoader, data_loader


class CurrentStateEngine:
    def __init__(self, loader: Optional[DataLoader] = None):
        self.loader = loader or data_loader
        self.isolation_forest: Optional[IsolationForest] = None
        self.model_path = config.models_dir / "isolation_forest.pkl"

        # Previous window cache for computing trend arrows: link_id -> speed_kph
        self.prev_speeds: Dict[str, float] = {}

        self._load_or_init_isolation_forest()

    def _load_or_init_isolation_forest(self) -> None:
        """Loads trained Isolation Forest model or trains a baseline one."""
        if self.model_path.exists():
            try:
                with open(self.model_path, "rb") as f:
                    self.isolation_forest = pickle.load(f)
                return
            except Exception as e:
                print(f"Warning: Failed to load Isolation Forest ({e}), fitting baseline...")

        # Synthetic calibration points for fast initial fit
        np.random.seed(42)
        normal_samples = np.random.normal(
            loc=[0.05, 0.02, 0.4, 0.3],
            scale=[0.08, 0.04, 0.15, 0.1],
            size=(2000, 4)
        )
        anomaly_samples = np.random.uniform(
            low=[0.4, 0.25, 0.8, 0.7],
            high=[0.9, 0.8, 1.3, 1.2],
            size=(100, 4)
        )
        X_init = np.vstack([normal_samples, anomaly_samples])
        iso = IsolationForest(
            contamination=config.isolation_forest_contamination,
            random_state=42,
            n_estimators=100
        )
        iso.fit(X_init)
        self.isolation_forest = iso

        try:
            with open(self.model_path, "wb") as f:
                pickle.dump(iso, f)
        except Exception:
            pass

    def compute_current_state(
        self,
        df_window: pd.DataFrame,
        forecasts: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Dict[str, Any]:
        """
        Analyzes the current streaming window (105 links) and produces:
        - Full link state list
        - Ranked Top 10 critical bottlenecks
        - Network-wide macroscopic summary
        """
        results = []
        road_class_weights = {
            "trunk": 1.25,
            "primary": 1.15,
            "secondary": 1.0,
            "residential": 0.85
        }

        # Prepare feature matrix for Isolation Forest batch scoring
        feature_rows = []
        raw_rows = []

        for _, row in df_window.iterrows():
            lid = row["link_id"]
            speed = float(row["speed_kph"])
            base_speed = max(10.0, float(row["baseline_speed_kph"]))
            occ = float(row["occupancy_pct"])
            vc = float(row["vc_ratio"])
            rc = str(row["road_class"])

            # 1. Speed drop vs baseline
            speed_drop = max(0.0, (base_speed - speed) / base_speed)
            speed_drop_pct = round(speed_drop * 100.0, 1)

            # 2. Occupancy spike
            base_occ = max(5.0, 12.0 * vc)
            occ_spike = max(0.0, (occ - base_occ) / 100.0)

            # 3. Stop-and-go / extreme congestion flag
            stop_and_go = speed < 12.0 and occ > 40.0

            # Features: [speed_drop, occ_spike, vc, occ/100]
            feature_rows.append([speed_drop, occ_spike, min(vc, 1.5), occ / 100.0])
            raw_rows.append((row, speed_drop_pct, occ_spike, stop_and_go, rc))

        # Batch compute ML anomaly scores
        X = np.array(feature_rows)
        if self.isolation_forest is not None:
            raw_scores = -self.isolation_forest.score_samples(X)  # Higher = more anomalous
            # Normalize to 0-100 scale
            min_s, max_s = -0.3, 0.4
            norm_scores = np.clip((raw_scores - min_s) / (max_s - min_s), 0.0, 1.0) * 100.0
        else:
            norm_scores = np.zeros(len(feature_rows))

        # Build comprehensive link states
        for idx, (row, speed_drop_pct, occ_spike, stop_and_go, rc) in enumerate(raw_rows):
            lid = row["link_id"]
            speed = float(row["speed_kph"])
            prev_speed = self.prev_speeds.get(lid, speed)
            delta_speed = speed - prev_speed

            # Trend arrow calculation
            if delta_speed < -2.5:
                trend = "worsening"
                trend_symbol = "↗"  # Worsening congestion (congestion rising)
            elif delta_speed > 2.5:
                trend = "improving"
                trend_symbol = "↘"  # Improving congestion (congestion falling)
            else:
                trend = "steady"
                trend_symbol = "→"

            # Composite severity score [0..100]
            ml_anomaly = float(norm_scores[idx])
            rc_weight = road_class_weights.get(rc, 1.0)

            severity = (
                (speed_drop_pct * 0.45) +
                (min(100.0, float(row["occupancy_pct"])) * 0.25) +
                (ml_anomaly * 0.20) +
                (min(1.5, float(row["vc_ratio"])) * 10.0)
            ) * rc_weight

            severity = round(min(100.0, max(0.0, severity)), 1)

            if severity >= 70:
                severity_level = "critical"
            elif severity >= 45:
                severity_level = "high"
            elif severity >= 25:
                severity_level = "moderate"
            else:
                severity_level = "low"

            # Check if this link has an active forecast attached
            link_forecast = {}
            confidence = 85.0
            if forecasts and lid in forecasts:
                link_forecast = forecasts[lid]
                confidence = float(link_forecast.get("confidence", 85.0))
            else:
                # Default heuristics if forecast not yet computed
                link_forecast = {
                    "+15m": round(max(3.0, speed * (0.95 if trend == "worsening" else 1.05)), 1),
                    "+30m": round(max(3.0, speed * (0.90 if trend == "worsening" else 1.10)), 1),
                    "+45m": round(max(3.0, speed * (0.88 if trend == "worsening" else 1.15)), 1),
                    "+60m": round(max(3.0, speed * (0.85 if trend == "worsening" else 1.20)), 1),
                }

            link_dict = {
                "link_id": lid,
                "name": row["name"],
                "road_class": rc,
                "u": row["u"],
                "v": row["v"],
                "speed_kph": speed,
                "baseline_speed_kph": float(row["baseline_speed_kph"]),
                "speed_drop_pct": speed_drop_pct,
                "flow_vph": float(row["flow_vph"]),
                "occupancy_pct": float(row["occupancy_pct"]),
                "density_veh_km_lane": float(row["density_veh_km_lane"]),
                "vc_ratio": float(row["vc_ratio"]),
                "level_of_service": row["level_of_service"],
                "anomaly_score": round(ml_anomaly, 1),
                "severity_score": severity,
                "severity_level": severity_level,
                "trend": trend,
                "trend_symbol": trend_symbol,
                "stop_and_go": stop_and_go,
                "forecast": link_forecast,
                "confidence": round(confidence, 1),
                "is_imputed": bool(row["is_imputed"]),
                "imputation_tier": row["imputation_tier"]
            }
            results.append(link_dict)
            self.prev_speeds[lid] = speed

        # Sort descending by severity score to produce Congestion Pulse
        results.sort(key=lambda x: x["severity_score"], reverse=True)
        top_10 = results[:10]

        # Network summary statistics
        speeds = [r["speed_kph"] for r in results]
        los_counts = {}
        for r in results:
            los_counts[r["level_of_service"]] = los_counts.get(r["level_of_service"], 0) + 1

        network_summary = {
            "total_links": len(results),
            "avg_speed_kph": round(float(np.mean(speeds)), 1),
            "critical_links_count": sum(1 for r in results if r["severity_level"] == "critical"),
            "high_links_count": sum(1 for r in results if r["severity_level"] == "high"),
            "los_breakdown": los_counts,
            "top_bottleneck_link": top_10[0]["link_id"] if top_10 else None
        }

        return {
            "all_links": results,
            "congestion_pulse_top10": top_10,
            "network_summary": network_summary
        }


current_state_engine = CurrentStateEngine()
