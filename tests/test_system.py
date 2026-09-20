"""
Traffic Pulse - Automated Test Suite
Verifies network topology, streaming pipeline, anomaly engine, incident classifier,
ST-GNN forecasting, operational advisories, infrastructure simulator, and API endpoints.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import networkx as nx
import numpy as np
import pandas as pd
from starlette.testclient import TestClient

from backend.config import config
from backend.data_loader import data_loader
from backend.pipeline import pipeline
from backend.current_state_engine import current_state_engine
from backend.incident_detector import incident_detector
from backend.forecasting_model import forecaster
from backend.advisory_engine import advisory_engine
from backend.infrastructure_recommender import infrastructure_recommender
from backend.server import app


class TestTrafficPulseSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.test_dt = pd.Timestamp("2024-01-01 16:50:00")

    def test_01_network_topology(self):
        """Verify network graph integrity, connectivity, and corridor chains."""
        self.assertEqual(len(data_loader.nodes_df), 36, "Network should have 36 nodes")
        self.assertEqual(len(data_loader.links_df), 105, "Network should have 105 links")
        self.assertTrue(nx.is_strongly_connected(data_loader.graph), "Network graph must be strongly connected")
        self.assertEqual(data_loader.adj_matrix.shape, (105, 105), "Adjacency matrix must be 105x105")

        # Verify corridors
        self.assertGreaterEqual(len(data_loader.corridors), 8, "Should extract at least 8 main corridors")
        for cid, cdata in data_loader.corridors.items():
            self.assertGreater(cdata["total_length_m"], 1000.0, f"Corridor {cid} length should be > 1000m")
            self.assertGreaterEqual(len(cdata["links"]), 4, f"Corridor {cid} should have at least 4 links")

    def test_02_pipeline_streaming_ingestion(self):
        """Verify streaming ingestion, cleaning, and gap imputation on 105-link grid."""
        df = pipeline.ingest_window(self.test_dt)
        self.assertEqual(len(df), 105, "Ingestion must align all 105 links in time-space grid")

        # Check physical bounds
        self.assertTrue((df["speed_kph"] >= 0.0).all(), "Speeds must be non-negative")
        self.assertTrue((df["occupancy_pct"] >= 0.0).all(), "Occupancy must be >= 0")
        self.assertTrue((df["occupancy_pct"] <= 100.0).all(), "Occupancy must be <= 100")
        self.assertTrue((df["flow_vph"] >= 0.0).all(), "Flow must be >= 0")

        # Verify baseline presence
        self.assertTrue("baseline_speed_kph" in df.columns, "Must contain baseline speed")
        self.assertTrue("imputation_tier" in df.columns, "Must trace imputation tier")

    def test_03_current_state_and_congestion_pulse(self):
        """Verify macroscopic parameter computation and top-10 bottleneck ranking."""
        df = pipeline.ingest_window(self.test_dt)
        state_out = current_state_engine.compute_current_state(df)

        top10 = state_out["congestion_pulse_top10"]
        self.assertEqual(len(top10), 10, "Congestion Pulse must rank top 10 links")

        # Verify descending severity sort
        severities = [item["severity_score"] for item in top10]
        self.assertEqual(severities, sorted(severities, reverse=True), "Top 10 must be sorted by severity descending")

        # Verify row fields
        first = top10[0]
        self.assertIn("severity_score", first)
        self.assertIn("speed_drop_pct", first)
        self.assertIn("trend", first)
        self.assertIn("forecast", first)
        self.assertIn("confidence", first)

    def test_04_incident_detection_and_classification(self):
        """Verify multi-modal incident detection and low-confidence guardrail."""
        df = pipeline.ingest_window(self.test_dt)
        state_out = current_state_engine.compute_current_state(df)
        incidents = incident_detector.detect_incidents(state_out["all_links"], self.test_dt)

        self.assertGreater(len(incidents), 0, "Must detect incidents during active collision window")

        # Verify structured evidence card schema
        for inc in incidents:
            self.assertIn("incident_id", inc)
            self.assertIn("link_id", inc)
            self.assertIn("type", inc)
            self.assertIn("confidence", inc)
            self.assertIn("triggering_signals", inc)
            self.assertIn("context", inc)
            self.assertIn("recommended_action", inc)

            # Low confidence guardrail check
            if inc["confidence"] < config.incident_confidence_threshold:
                self.assertEqual(
                    inc["type"],
                    "abnormal_behavior",
                    "Incidents with confidence < threshold must be labeled abnormal_behavior only"
                )

    def test_05_st_gnn_forecasting(self):
        """Verify Spatiotemporal GNN multi-horizon predictions (+15, +30, +45, +60m)."""
        df = pipeline.ingest_window(self.test_dt)
        forecasts = forecaster.predict(df.to_dict("records"), dt=self.test_dt)

        self.assertEqual(len(forecasts), 105, "ST-GNN must forecast all 105 links simultaneously")

        # Check horizons on sample link
        sample_fc = forecasts["L00000"]
        for h in ["+15m", "+30m", "+45m", "+60m"]:
            self.assertIn(h, sample_fc, f"Missing horizon {h} in forecast")
            self.assertGreater(sample_fc[h], 0.0, f"Speed forecast for {h} must be positive")
            self.assertIn(f"flow_{h}", sample_fc, f"Missing flow horizon flow_{h}")

        self.assertGreaterEqual(sample_fc["confidence"], 50.0, "Forecast confidence must be realistic")

    def test_06_advisory_engine_and_human_in_loop(self):
        """Verify alternate route computation, Webster signal retiming, and approval recording."""
        df = pipeline.ingest_window(self.test_dt)
        state_out = current_state_engine.compute_current_state(df)
        incidents = incident_detector.detect_incidents(state_out["all_links"], self.test_dt)
        advisories = advisory_engine.generate_advisories(state_out["all_links"], incidents, self.test_dt)

        self.assertGreater(len(advisories), 0, "Should generate operational advisories for severe bottlenecks")

        # Test human-in-the-loop decision
        first_adv = advisories[0]
        adv_id = first_adv["advisory_id"]
        rec = advisory_engine.record_decision(adv_id, "APPROVE", "Operator approved via test")
        self.assertEqual(rec["action"], "APPROVE")
        self.assertEqual(advisory_engine.active_advisories[adv_id]["status"], "APPROVE")

    def test_07_infrastructure_recommender_and_simulator(self):
        """Verify bottleneck clustering and 24-hour Before/After dynamic simulation."""
        self.assertEqual(len(infrastructure_recommender.bottleneck_clusters), 4, "Must identify 4 bottleneck clusters")
        self.assertGreaterEqual(len(infrastructure_recommender.projects), 4, "Must propose at least 4 engineering projects")

        sim = infrastructure_recommender.simulate_project_impact("PROJ-LANE-EW-TRU")
        sum_m = sim["metrics_summary"]
        self.assertGreater(sum_m["speed_improvement_pct"], 0.0, "Should show speed improvement after lane addition")
        self.assertGreater(sum_m["queue_reduction_pct"], 0.0, "Should show queue reduction after lane addition")
        self.assertEqual(len(sim["replay_timeline_24h"]), 144, "24h replay must contain 144 10-minute intervals")

    def test_08_rest_api_endpoints(self):
        """Verify REST API response schemas and status codes."""
        # 1. Network API
        r = self.client.get("/api/network")
        self.assertEqual(r.status_code, 200)
        net_data = r.json()
        self.assertEqual(net_data["links_count"], 105)

        # 2. Current State API
        r = self.client.get("/api/current_state")
        self.assertEqual(r.status_code, 200)
        st_data = r.json()
        self.assertEqual(len(st_data["congestion_pulse_top10"]), 10)

        # 3. Corridor Timeline Strip API
        r = self.client.get("/api/corridor_timeline?corridor=EW-TRU-EB")
        self.assertEqual(r.status_code, 200)
        ctl_data = r.json()
        self.assertIn("timeline_rows", ctl_data)
        self.assertGreater(len(ctl_data["timeline_rows"]), 10)

        # 4. Infrastructure Simulate API
        r = self.client.get("/api/infrastructure/simulate?project_id=PROJ-LANE-EW-TRU")
        self.assertEqual(r.status_code, 200)
        sim_data = r.json()
        self.assertIn("metrics_summary", sim_data)

        # 5. Playback API
        r = self.client.post("/api/playback", json={"action": "step"})
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
