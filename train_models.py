"""
Traffic Pulse - Model Training & Pre-caching Suite
Trains and saves:
1. Spatiotemporal ST-GNN multi-horizon forecasting weights
2. Isolation Forest multivariate anomaly detector
3. Multi-modal Incident Classifier (with low-confidence abnormal behavior support)
4. 90-day Recurring Bottleneck Clustering index
"""

from __future__ import annotations

import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim

from backend.config import config
from backend.data_loader import data_loader
from backend.pipeline import pipeline
from backend.current_state_engine import current_state_engine
from backend.incident_detector import incident_detector
from backend.forecasting_model import forecaster, SpatioTemporalGNN
from backend.infrastructure_recommender import infrastructure_recommender


def train_st_gnn():
    print("\n--- Training Spatiotemporal Graph Neural Network (ST-GNN) ---")
    device = torch.device("cpu")
    num_nodes = len(data_loader.links_df)
    horizons = config.forecast_horizons

    model = SpatioTemporalGNN(
        num_nodes=num_nodes,
        in_features=5,
        hidden_dim=config.st_gnn_hidden_dim,
        num_horizons=len(horizons)
    ).to(device)

    # Prepare training sequences from sample ground truth slices
    print("Generating spatiotemporal training batches...")
    optimizer = optim.Adam(model.parameters(), lr=0.003, weight_decay=1e-4)
    criterion = nn.MSELoss()

    adj_norm = forecaster.adj_norm_tensor

    # Generate synthetic training trajectories based on real graph topologies
    X_train_list = []
    y_train_list = []

    np.random.seed(42)
    for _ in range(40):
        # 6 timesteps lookback, 105 links, 5 features
        seq = []
        base_demand = np.random.uniform(0.3, 0.95)
        for t in range(6):
            step = []
            for idx, lid in enumerate(data_loader.links_df["link_id"]):
                info = data_loader.get_link_info(lid)
                ff = float(info["free_flow_speed_kph"])
                cap = float(info["capacity_vph"])

                # Spatial wave fluctuation
                rand_fluct = np.random.normal(0, 0.05)
                spd_ratio = max(0.1, min(1.1, (1.0 - 0.4 * base_demand) + rand_fluct))
                flow_ratio = max(0.1, min(1.2, base_demand + rand_fluct))
                occ = flow_ratio * 0.4
                step.append([spd_ratio, flow_ratio, occ, 0.5, 0.5])
            seq.append(step)
        X_train_list.append(seq)

        # Target: 4 horizons x 105 links x 2 (spd_ratio, flow_ratio)
        target = []
        for h in range(len(horizons)):
            h_step = []
            for idx, lid in enumerate(data_loader.links_df["link_id"]):
                decay = 0.02 * (h + 1)
                h_step.append([max(0.1, spd_ratio - decay), flow_ratio])
            target.append(h_step)
        y_train_list.append(target)

    X_train = torch.tensor(X_train_list, dtype=torch.float32, device=device)
    y_train = torch.tensor(y_train_list, dtype=torch.float32, device=device)

    model.train()
    start_t = time.time()
    for epoch in range(config.st_gnn_epochs):
        optimizer.zero_grad()
        out = model(X_train, adj_norm)
        loss = criterion(out, y_train)
        loss.backward()
        optimizer.step()
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"Epoch {epoch+1:02d}/{config.st_gnn_epochs} | ST-GNN MSE Loss: {loss.item():.5f}")

    elapsed = time.time() - start_t
    print(f"ST-GNN Training complete in {elapsed:.2f}s!")

    # Save weights
    save_path = config.models_dir / "st_gnn_traffic.pt"
    torch.save(model.state_dict(), save_path)
    print(f"Model saved to: {save_path}")


def train_isolation_forest():
    print("\n--- Fitting Isolation Forest Anomaly Model ---")
    current_state_engine._load_or_init_isolation_forest()
    print("Isolation Forest ready and cached at:", current_state_engine.model_path)


def train_incident_classifier():
    print("\n--- Training Incident Classifier ---")
    incident_detector._train_from_data()
    print("Incident Classifier trained and saved at:", incident_detector.model_path)


def build_bottlenecks():
    print("\n--- Indexing 90-Day Bottleneck Clusters ---")
    infrastructure_recommender._build_bottlenecks_and_projects()
    print(f"Indexed {len(infrastructure_recommender.bottleneck_clusters)} clusters and {len(infrastructure_recommender.projects)} projects!")


def main():
    print("=================================================================")
    print("Traffic Pulse - AI Model Training & Offline Calibration Suite")
    print("=================================================================")
    train_isolation_forest()
    train_incident_classifier()
    train_st_gnn()
    build_bottlenecks()
    print("\nAll models trained, calibrated, and ready for production operations!")


if __name__ == "__main__":
    main()
