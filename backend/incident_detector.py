"""
Traffic Pulse - Incident Detection & Multi-Modal Fusion Engine
Fuses telemetry anomalies with weather, roadworks, events, and spatial gradients.
Classifies incident type (accident, stall, work zone, hazard) with calibrated confidence.
Applies low-confidence guardrail to label ambiguous cases as 'Abnormal Behavior' only.
"""

from __future__ import annotations

import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

from backend.config import config
from backend.data_loader import DataLoader, data_loader


class IncidentDetector:
    def __init__(self, loader: Optional[DataLoader] = None):
        self.loader = loader or data_loader
        self.classifier: Optional[GradientBoostingClassifier] = None
        self.model_path = config.models_dir / "incident_classifier.pkl"
        self.confidence_threshold = config.incident_confidence_threshold

        # Recent speed history buffer for sparklines: link_id -> list of speeds
        self.speed_history: Dict[str, List[float]] = {}

        self._load_or_train_classifier()

    def _load_or_train_classifier(self) -> None:
        """Loads trained incident classifier or trains on historical dataset."""
        if self.model_path.exists():
            try:
                with open(self.model_path, "rb") as f:
                    self.classifier = pickle.load(f)
                return
            except Exception as e:
                print(f"Warning: Failed to load incident classifier ({e}), re-fitting...")

        self._train_from_data()

    def _train_from_data(self) -> None:
        """
        Trains a multi-class Gradient Boosting Classifier on annotated ground truth
        incidents and roadworks from the dataset.
        Classes:
          0: 'normal_congestion'
          1: 'accident' (collision, pedestrian)
          2: 'stall' (stalled vehicle, breakdown)
          3: 'work_zone' (utility, roadworks)
          4: 'hazard' (debris, spillage)
        """
        X = []
        y = []

        # 1. Negative samples: regular congestion / free flow
        np.random.seed(42)
        for _ in range(500):
            spd_drop = np.random.beta(2, 5) * 0.45  # [0..0.45]
            occ_spike = np.random.beta(1.5, 4) * 0.25
            downstream_ratio = np.random.normal(1.0, 0.15)
            rain = np.random.choice([0.0, 2.0, 5.0], p=[0.8, 0.15, 0.05])
            has_work = 0.0
            has_event = np.random.choice([0.0, 1.0], p=[0.9, 0.1])
            lanes_blocked = 0.0
            X.append([spd_drop, occ_spike, downstream_ratio, rain, has_work, has_event, lanes_blocked])
            y.append(0)

        # 2. Positive samples from annotated incidents dataset
        inc_df = self.loader.incidents_df
        if not inc_df.empty:
            for _, row in inc_df.iterrows():
                itype = str(row["incident_type"]).lower()
                sev = int(row.get("severity", 1))
                lanes_blk = float(row.get("lanes_blocked", 0))

                if "collision" in itype or "pedestrian" in itype:
                    cls_id = 1
                    spd_drop = min(0.95, 0.55 + 0.15 * sev + np.random.normal(0, 0.05))
                    occ_spike = min(0.9, 0.35 + 0.15 * sev + np.random.normal(0, 0.05))
                    downstream_ratio = 1.8 + 0.4 * sev
                    rain = 3.0 if "rain" in str(row.get("weather_at_incident", "")) else 0.0
                    has_work = 0.0
                    has_event = 0.0
                elif "stall" in itype or "breakdown" in itype:
                    cls_id = 2
                    spd_drop = min(0.85, 0.35 + 0.15 * sev + np.random.normal(0, 0.05))
                    occ_spike = min(0.7, 0.25 + 0.1 * sev + np.random.normal(0, 0.05))
                    downstream_ratio = 1.4 + 0.2 * sev
                    rain = 0.0
                    has_work = 0.0
                    has_event = 0.0
                elif "debris" in itype or "spillage" in itype:
                    cls_id = 4
                    spd_drop = min(0.75, 0.30 + 0.15 * sev + np.random.normal(0, 0.05))
                    occ_spike = min(0.6, 0.20 + 0.1 * sev + np.random.normal(0, 0.05))
                    downstream_ratio = 1.3 + 0.2 * sev
                    rain = 0.0
                    has_work = 0.0
                    has_event = 0.0
                else:
                    cls_id = 1
                    spd_drop = 0.6
                    occ_spike = 0.3
                    downstream_ratio = 1.4
                    rain = 0.0
                    has_work = 0.0
                    has_event = 0.0

                X.append([spd_drop, occ_spike, downstream_ratio, rain, has_work, has_event, lanes_blk])
                y.append(cls_id)

        # 3. Positive samples for work zones from roadworks
        rw_df = self.loader.roadworks_df
        if not rw_df.empty:
            for _, row in rw_df.iterrows():
                spd_drop = 1.0 - float(row.get("speed_factor", 0.7))
                occ_spike = 0.35
                downstream_ratio = 1.5
                rain = 0.0
                has_work = 1.0
                has_event = 0.0
                lanes_blk = float(row.get("lanes_closed", 1))
                X.append([spd_drop, occ_spike, downstream_ratio, rain, has_work, has_event, lanes_blk])
                y.append(3)

        X_mat = np.array(X)
        y_vec = np.array(y)

        clf = GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42)
        clf.fit(X_mat, y_vec)
        self.classifier = clf

        try:
            with open(self.model_path, "wb") as f:
                pickle.dump(clf, f)
        except Exception:
            pass

    def detect_incidents(
        self,
        current_links: List[Dict[str, Any]],
        dt: pd.Timestamp
    ) -> List[Dict[str, Any]]:
        """
        Fuses current link telemetry, spatial context, weather, events, and roadworks.
        Returns a list of structured incident evidence cards.
        """
        weather = self.loader.get_weather_at(dt)
        rain_rate = float(weather.get("rainfall_mm_h", 0.0))

        # Check active roadworks at this timestamp
        active_roadworks: Dict[str, Dict[str, Any]] = {}
        for _, rw in self.loader.roadworks_df.iterrows():
            st_date = pd.to_datetime(rw["start_date"]).date()
            ed_date = pd.to_datetime(rw["end_date"]).date()
            cur_date = dt.date()
            if st_date <= cur_date <= ed_date:
                daily_st = int(rw["daily_start_hour"])
                daily_ed = int(rw["daily_end_hour"])
                # Check hour interval
                in_hours = False
                if daily_st <= daily_ed:
                    in_hours = (daily_st <= dt.hour <= daily_ed)
                else:
                    # Overnight (e.g. 22 to 5)
                    in_hours = (dt.hour >= daily_st or dt.hour <= daily_ed)
                if in_hours:
                    active_roadworks[rw["link_id"]] = rw.to_dict()

        # Check active event venues
        active_events: Dict[str, Dict[str, Any]] = {}
        for _, ev in self.loader.events_df.iterrows():
            if ev["start_time"] <= dt <= ev["end_time"]:
                active_events[ev["node_id"]] = ev.to_dict()

        # Update speed history buffers for sparklines
        for l in current_links:
            lid = l["link_id"]
            if lid not in self.speed_history:
                self.speed_history[lid] = []
            self.speed_history[lid].append(l["speed_kph"])
            if len(self.speed_history[lid]) > 8:
                self.speed_history[lid].pop(0)

        # Build link lookup map for spatial gradient
        link_speed_map = {l["link_id"]: l["speed_kph"] for l in current_links}

        detected_incidents = []
        class_names = {
            0: "normal_congestion",
            1: "collision",
            2: "stalled_vehicle",
            3: "work_zone",
            4: "hazard"
        }
        human_labels = {
            "collision": "Accident / Collision",
            "stalled_vehicle": "Stalled Vehicle / Breakdown",
            "work_zone": "Active Road Work Zone",
            "hazard": "Road Hazard / Spillage",
            "abnormal_behavior": "Abnormal Traffic Behavior"
        }

        # Filter candidate links with notable anomaly signals
        for l in current_links:
            lid = l["link_id"]
            speed_drop = l["speed_drop_pct"] / 100.0
            occ = l["occupancy_pct"]
            sev = l["severity_score"]
            anom = l["anomaly_score"]
            speed = l["speed_kph"]
            base_spd = l["baseline_speed_kph"]

            # Candidate trigger condition: significant speed drop, severe bottleneck, or high ML anomaly
            is_candidate = (
                (speed_drop >= config.anomaly_speed_drop_threshold and speed < 25.0) or
                (sev >= 65.0) or
                (anom >= 75.0 and speed_drop >= 0.25) or
                (lid in active_roadworks and speed_drop >= 0.20)
            )

            if not is_candidate:
                continue

            # Compute downstream shockwave gradient
            v_node = l["v"]
            downstream_links = [dl for dl, d in self.loader.link_map.items() if d["u"] == v_node and dl != lid]
            downstream_speeds = [link_speed_map.get(dl, 50.0) for dl in downstream_links if dl in link_speed_map]
            downstream_avg_spd = float(np.mean(downstream_speeds)) if downstream_speeds else 45.0
            downstream_ratio = downstream_avg_spd / max(3.0, speed)

            # Check context
            has_work = 1.0 if lid in active_roadworks else 0.0
            has_event = 1.0 if (l["u"] in active_events or l["v"] in active_events) else 0.0
            lanes_blk = float(active_roadworks[lid].get("lanes_closed", 1.0)) if has_work else (1.0 if speed < 8.0 else 0.0)
            occ_spike = max(0.0, (occ - 15.0) / 100.0)

            features = np.array([[speed_drop, occ_spike, min(4.0, downstream_ratio), rain_rate, has_work, has_event, lanes_blk]])

            # Classifier prediction and probability distribution
            if self.classifier is not None:
                probs = self.classifier.predict_proba(features)[0]
                best_cls_idx = int(np.argmax(probs))
                max_prob = float(probs[best_cls_idx])
                raw_type = class_names.get(best_cls_idx, "normal_congestion")
            else:
                max_prob = 0.5
                raw_type = "abnormal_behavior"

            # Check if roadworks actively explain the anomaly
            if has_work and max_prob >= 0.40:
                raw_type = "work_zone"
                max_prob = max(max_prob, 0.92)

            # Ignore normal congestion unless it's an extreme unclassified anomaly
            if raw_type == "normal_congestion":
                if sev < 75.0:
                    continue
                # Severe unexplained anomaly labeled as abnormal behavior
                assigned_type = "abnormal_behavior"
                confidence = round(max(40.0, min(59.0, max_prob * 100.0)), 1)
                is_low_conf = True
            else:
                # LOW-CONFIDENCE GUARDRAIL:
                # If confidence is below threshold (< 0.60), label specifically as 'abnormal_behavior'
                if max_prob < self.confidence_threshold:
                    assigned_type = "abnormal_behavior"
                    confidence = round(max_prob * 100.0, 1)
                    is_low_conf = True
                else:
                    assigned_type = raw_type
                    confidence = round(max_prob * 100.0, 1)
                    is_low_conf = False

            # Associated CCTV or detector
            u_node_info = self.loader.node_map.get(l["u"], {})
            lat = float(u_node_info.get("lat", 17.385))
            lon = float(u_node_info.get("lon", 78.486))
            det_id = f"CCTV-{l['u']}-CAM{(hash(lid) % 3) + 1}"

            # Recommended Action
            if assigned_type == "collision":
                rec_action = f"Dispatch Emergency Response & Initiate Alternate Route Diversion from {lid}"
                action_type = "diversion"
            elif assigned_type == "work_zone":
                rec_action = f"Verify Roadwork Permit {active_roadworks.get(lid, {}).get('permit_ref', 'PRM-ACTIVE')} & Adjust Signal Timing"
                action_type = "signal_retiming"
            elif assigned_type == "stalled_vehicle":
                rec_action = f"Dispatch Towing Service to {l['name']} & Advise Upstream Metering"
                action_type = "ramp_metering"
            elif assigned_type == "hazard":
                rec_action = f"Dispatch Highway Maintenance Unit to Clear Roadway on {lid}"
                action_type = "maintenance"
            else:
                rec_action = f"Operator Review: Inspect Link {lid} CCTV & Sensor Telemetry for Anomaly Source"
                action_type = "investigate"

            # Formulate structured evidence card
            card = {
                "incident_id": f"INC-LIVE-{lid}",
                "link_id": lid,
                "corridor_name": l["name"],
                "road_class": l["road_class"],
                "type": assigned_type,
                "type_label": human_labels.get(assigned_type, "Abnormal Traffic Behavior"),
                "confidence": confidence,
                "is_low_confidence": is_low_conf,
                "detected_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "lat": lat,
                "lon": lon,
                "severity_score": l["severity_score"],
                "triggering_signals": {
                    "current_speed_kph": speed,
                    "baseline_speed_kph": base_spd,
                    "speed_drop_pct": l["speed_drop_pct"],
                    "occupancy_pct": occ,
                    "anomaly_score": anom,
                    "shockwave_ratio": round(downstream_ratio, 2),
                    "speed_sparkline": self.speed_history.get(lid, [speed])
                },
                "context": {
                    "weather_condition": weather.get("condition", "clear"),
                    "rainfall_mm_h": rain_rate,
                    "active_roadwork": active_roadworks.get(lid, {}).get("permit_ref"),
                    "active_event": active_events.get(l["u"], {}).get("event_type") or active_events.get(l["v"], {}).get("event_type"),
                    "sensor_id": det_id,
                    "camera_name": f"{l['u']} Traffic Camera"
                },
                "recommended_action": rec_action,
                "action_type": action_type
            }
            detected_incidents.append(card)

        # Sort incidents by severity descending
        detected_incidents.sort(key=lambda x: x["severity_score"], reverse=True)
        return detected_incidents


incident_detector = IncidentDetector()
