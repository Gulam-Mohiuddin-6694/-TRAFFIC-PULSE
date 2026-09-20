"""
Traffic Pulse - Network & Static Data Loader
Loads graph topology, GeoJSON geometries, detectors, weather, events, and corridors.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd

from backend.config import config


class DataLoader:
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else config.data_dir
        self.network_dir = self.data_dir / "network"
        self.traffic_dir = self.data_dir / "traffic"
        self.weather_dir = self.data_dir / "weather"
        self.events_dir = self.data_dir / "events"
        self.incidents_dir = self.data_dir / "incidents"
        self.probes_dir = self.data_dir / "probes"

        # Cached datasets
        self.nodes_df: pd.DataFrame = pd.DataFrame()
        self.links_df: pd.DataFrame = pd.DataFrame()
        self.detectors_df: pd.DataFrame = pd.DataFrame()
        self.network_geojson: Dict[str, Any] = {}
        self.signal_plans_df: pd.DataFrame = pd.DataFrame()
        self.signal_phases_df: pd.DataFrame = pd.DataFrame()
        self.weather_df: pd.DataFrame = pd.DataFrame()
        self.events_df: pd.DataFrame = pd.DataFrame()
        self.roadworks_df: pd.DataFrame = pd.DataFrame()
        self.incidents_df: pd.DataFrame = pd.DataFrame()

        # Graph objects
        self.graph: nx.DiGraph = nx.DiGraph()
        self.link_map: Dict[str, Dict[str, Any]] = {}
        self.node_map: Dict[str, Dict[str, Any]] = {}
        self.link_id_to_idx: Dict[str, int] = {}
        self.idx_to_link_id: Dict[int, str] = {}
        self.adj_matrix: np.ndarray = np.zeros((105, 105), dtype=np.float32)
        self.corridors: Dict[str, List[Dict[str, Any]]] = {}

        self.load_all()

    def load_all(self) -> None:
        """Loads all static datasets and builds network graphs."""
        self._load_network()
        self._load_detectors()
        self._load_weather()
        self._load_events_and_works()
        self._load_incidents()
        self._build_corridors()

    def _load_network(self) -> None:
        nodes_path = self.network_dir / "nodes.csv"
        links_path = self.network_dir / "links.csv"
        geojson_path = self.network_dir / "network.geojson"

        if not links_path.exists():
            raise FileNotFoundError(f"Links file not found: {links_path}")

        self.nodes_df = pd.read_csv(nodes_path)
        self.links_df = pd.read_csv(links_path)

        with open(geojson_path, "r", encoding="utf-8") as f:
            self.network_geojson = json.load(f)

        # Signal configs
        sp_path = self.network_dir / "signal_plans.csv"
        if sp_path.exists():
            self.signal_plans_df = pd.read_csv(sp_path)
        sph_path = self.network_dir / "signal_phases.csv"
        if sph_path.exists():
            self.signal_phases_df = pd.read_csv(sph_path)

        # Node index map
        for _, row in self.nodes_df.iterrows():
            self.node_map[row["node_id"]] = row.to_dict()

        # Link index map and NetworkX graph
        self.graph = nx.DiGraph()
        for idx, row in self.links_df.iterrows():
            lid = row["link_id"]
            self.link_id_to_idx[lid] = idx
            self.idx_to_link_id[idx] = lid
            info = row.to_dict()
            self.link_map[lid] = info
            self.graph.add_edge(
                row["u"],
                row["v"],
                link_id=lid,
                length=float(row["length_m"]),
                speed_limit=float(row["speed_limit_kph"]),
                free_flow_speed=float(row["free_flow_speed_kph"]),
                capacity=float(row["capacity_vph"]),
                lanes=int(row["lanes"]),
                name=row["name"],
                road_class=row["road_class"]
            )

        # Build 105x105 Topological Link Adjacency Matrix
        # Link A -> Link B if destination node v(A) == origin node u(B)
        n_links = len(self.links_df)
        self.adj_matrix = np.zeros((n_links, n_links), dtype=np.float32)
        for i, r_i in self.links_df.iterrows():
            for j, r_j in self.links_df.iterrows():
                if r_i["v"] == r_j["u"] and r_i["link_id"] != r_j["link_id"]:
                    self.adj_matrix[i, j] = 1.0

    def _load_detectors(self) -> None:
        det_path = self.traffic_dir / "detectors.csv"
        if det_path.exists():
            self.detectors_df = pd.read_csv(det_path)
        else:
            self.detectors_df = pd.DataFrame()

    def _load_weather(self) -> None:
        w_path = self.weather_dir / "weather_hourly.csv"
        if w_path.exists():
            self.weather_df = pd.read_csv(w_path)
            self.weather_df["timestamp"] = pd.to_datetime(self.weather_df["timestamp"])
            self.weather_df.set_index("timestamp", inplace=True)

    def _load_events_and_works(self) -> None:
        ev_path = self.events_dir / "events.csv"
        if ev_path.exists():
            self.events_df = pd.read_csv(ev_path)
            self.events_df["start_time"] = pd.to_datetime(self.events_df["start_time"])
            self.events_df["end_time"] = pd.to_datetime(self.events_df["end_time"])

        rw_path = self.events_dir / "roadworks_closures.csv"
        if rw_path.exists():
            self.roadworks_df = pd.read_csv(rw_path)

    def _load_incidents(self) -> None:
        inc_path = self.incidents_dir / "incidents.csv"
        if inc_path.exists():
            self.incidents_df = pd.read_csv(inc_path)
            self.incidents_df["start_time"] = pd.to_datetime(self.incidents_df["start_time"])
            self.incidents_df["clearance_time"] = pd.to_datetime(self.incidents_df["clearance_time"])

    def _build_corridors(self) -> None:
        """
        Builds ordered chains of links representing physical travel corridors
        with cumulative meter offsets along each corridor.
        """
        # Define the main corridors in the 6x6 grid
        corridor_specs = [
            ("EW-TRU-EB", "East-West Trunk (Eastbound)", 0, "E"),
            ("EW-TRU-WB", "East-West Trunk (Westbound)", 0, "W"),
            ("EW-PRI-EB", "East-West Primary (Eastbound)", 3, "E"),
            ("EW-PRI-WB", "East-West Primary (Westbound)", 3, "W"),
            ("EW-SEC-EB", "East-West Secondary (Eastbound)", 2, "E"),
            ("EW-SEC-WB", "East-West Secondary (Westbound)", 2, "W"),
            ("NS-TRU-NB", "North-South Trunk (Northbound)", 0, "N"),
            ("NS-TRU-SB", "North-South Trunk (Southbound)", 0, "S"),
            ("NS-PRI-NB", "North-South Primary (Northbound)", 3, "N"),
            ("NS-PRI-SB", "North-South Primary (Southbound)", 3, "S"),
        ]

        for cid, label, row_or_col, direction in corridor_specs:
            chain = []
            cum_dist = 0.0

            if direction == "E":
                # row fixed, col 0 -> 5
                row = row_or_col
                for col in range(5):
                    u_node = f"N0{row}0{col}"
                    v_node = f"N0{row}0{col+1}"
                    match = self.links_df[(self.links_df["u"] == u_node) & (self.links_df["v"] == v_node)]
                    if not match.empty:
                        link_row = match.iloc[0]
                        length = float(link_row["length_m"])
                        chain.append({
                            "link_id": link_row["link_id"],
                            "name": link_row["name"],
                            "u": u_node,
                            "v": v_node,
                            "start_m": cum_dist,
                            "end_m": cum_dist + length,
                            "length_m": length,
                            "speed_limit_kph": float(link_row["speed_limit_kph"]),
                            "free_flow_speed_kph": float(link_row["free_flow_speed_kph"]),
                            "lanes": int(link_row["lanes"]),
                            "road_class": link_row["road_class"]
                        })
                        cum_dist += length

            elif direction == "W":
                # row fixed, col 5 -> 0
                row = row_or_col
                for col in range(5, 0, -1):
                    u_node = f"N0{row}0{col}"
                    v_node = f"N0{row}0{col-1}"
                    match = self.links_df[(self.links_df["u"] == u_node) & (self.links_df["v"] == v_node)]
                    if not match.empty:
                        link_row = match.iloc[0]
                        length = float(link_row["length_m"])
                        chain.append({
                            "link_id": link_row["link_id"],
                            "name": link_row["name"],
                            "u": u_node,
                            "v": v_node,
                            "start_m": cum_dist,
                            "end_m": cum_dist + length,
                            "length_m": length,
                            "speed_limit_kph": float(link_row["speed_limit_kph"]),
                            "free_flow_speed_kph": float(link_row["free_flow_speed_kph"]),
                            "lanes": int(link_row["lanes"]),
                            "road_class": link_row["road_class"]
                        })
                        cum_dist += length

            elif direction == "N":
                # col fixed, row 0 -> 5
                col = row_or_col
                for row in range(5):
                    u_node = f"N0{row}0{col}"
                    v_node = f"N0{row+1}0{col}"
                    match = self.links_df[(self.links_df["u"] == u_node) & (self.links_df["v"] == v_node)]
                    if not match.empty:
                        link_row = match.iloc[0]
                        length = float(link_row["length_m"])
                        chain.append({
                            "link_id": link_row["link_id"],
                            "name": link_row["name"],
                            "u": u_node,
                            "v": v_node,
                            "start_m": cum_dist,
                            "end_m": cum_dist + length,
                            "length_m": length,
                            "speed_limit_kph": float(link_row["speed_limit_kph"]),
                            "free_flow_speed_kph": float(link_row["free_flow_speed_kph"]),
                            "lanes": int(link_row["lanes"]),
                            "road_class": link_row["road_class"]
                        })
                        cum_dist += length

            elif direction == "S":
                # col fixed, row 5 -> 0
                col = row_or_col
                for row in range(5, 0, -1):
                    u_node = f"N0{row}0{col}"
                    v_node = f"N0{row-1}0{col}"
                    match = self.links_df[(self.links_df["u"] == u_node) & (self.links_df["v"] == v_node)]
                    if not match.empty:
                        link_row = match.iloc[0]
                        length = float(link_row["length_m"])
                        chain.append({
                            "link_id": link_row["link_id"],
                            "name": link_row["name"],
                            "u": u_node,
                            "v": v_node,
                            "start_m": cum_dist,
                            "end_m": cum_dist + length,
                            "length_m": length,
                            "speed_limit_kph": float(link_row["speed_limit_kph"]),
                            "free_flow_speed_kph": float(link_row["free_flow_speed_kph"]),
                            "lanes": int(link_row["lanes"]),
                            "road_class": link_row["road_class"]
                        })
                        cum_dist += length

            if chain:
                self.corridors[cid] = {
                    "id": cid,
                    "label": label,
                    "total_length_m": cum_dist,
                    "links": chain
                }

    def get_link_info(self, link_id: str) -> Optional[Dict[str, Any]]:
        return self.link_map.get(link_id)

    def get_weather_at(self, dt: pd.Timestamp) -> Dict[str, Any]:
        """Returns weather attributes for the floored hour of dt."""
        hour_ts = dt.floor("h")
        if hour_ts in self.weather_df.index:
            return self.weather_df.loc[hour_ts].to_dict()
        return {
            "rainfall_mm_h": 0.0,
            "condition": "clear",
            "visibility_km": 10.0,
            "capacity_factor": 1.0,
            "speed_factor": 1.0,
            "incident_risk_multiplier": 1.0
        }


# Global shared instance
data_loader = DataLoader()
