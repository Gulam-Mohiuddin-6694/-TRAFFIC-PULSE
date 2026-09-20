/**
 * Traffic Pulse - View 6: Map as a Secondary Layer
 * Geography is context, not the primary UI. Minimalist dark network map drill-down
 * with real-time speed/LOS overlay and link telemetry inspector panel.
 */

const SecondaryMap = {
  map: null,
  geojsonLayer: null,
  currentLinkStates: {},
  selectedLinkId: null,

  initMap(geojson) {
    if (this.map) return;
    const mapEl = document.getElementById("network-map");
    if (!mapEl) return;

    // Center coordinates from dataset metadata (Hyderabad test grid: 17.385, 78.4867)
    this.map = L.map("network-map", {
      center: [17.385, 78.4867],
      zoom: 14,
      zoomControl: true
    });

    // Dark-mode basemap tiles
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
      subdomains: "abcd",
      maxZoom: 19
    }).addTo(this.map);

    if (geojson) {
      this.loadGeoJSON(geojson);
    }

    const resetBtn = document.getElementById("btn-map-fit");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        if (this.geojsonLayer) {
          this.map.fitBounds(this.geojsonLayer.getBounds(), { padding: [30, 30] });
        }
      });
    }
  },

  invalidateSize() {
    if (this.map) {
      setTimeout(() => this.map.invalidateSize(), 150);
    }
  },

  getColorForLink(lid) {
    const st = this.currentLinkStates[lid];
    if (!st) return "#38bdf8";
    const los = st.level_of_service || "A";
    if (los === "F") return "#ef4444";
    if (los === "E") return "#f97316";
    if (los === "D") return "#f59e0b";
    if (los === "C") return "#fbbf24";
    if (los === "B") return "#34d399";
    return "#10b981";
  },

  loadGeoJSON(geojson) {
    if (this.geojsonLayer) {
      this.map.removeLayer(this.geojsonLayer);
    }

    this.geojsonLayer = L.geoJSON(geojson, {
      style: (feature) => {
        const lid = feature.properties.link_id;
        const color = this.getColorForLink(lid);
        const isSelected = (lid === this.selectedLinkId);

        return {
          color: isSelected ? "#38bdf8" : color,
          weight: isSelected ? 6 : 4,
          opacity: isSelected ? 1.0 : 0.85
        };
      },
      onEachFeature: (feature, layer) => {
        const p = feature.properties;
        layer.on({
          click: () => {
            this.selectLink(p.link_id);
          },
          mouseover: () => {
            layer.setStyle({ weight: 6, opacity: 1.0 });
          },
          mouseout: () => {
            if (p.link_id !== this.selectedLinkId) {
              layer.setStyle({
                weight: 4,
                opacity: 0.85,
                color: this.getColorForLink(p.link_id)
              });
            }
          }
        });
      }
    }).addTo(this.map);

    this.map.fitBounds(this.geojsonLayer.getBounds(), { padding: [30, 30] });
  },

  updateLinkStates(allLinks) {
    (allLinks || []).forEach(l => {
      this.currentLinkStates[l.link_id] = l;
    });

    // Refresh layer colors
    if (this.geojsonLayer) {
      this.geojsonLayer.setStyle((feature) => {
        const lid = feature.properties.link_id;
        const color = this.getColorForLink(lid);
        const isSelected = (lid === this.selectedLinkId);

        return {
          color: isSelected ? "#38bdf8" : color,
          weight: isSelected ? 6 : 4,
          opacity: isSelected ? 1.0 : 0.85
        };
      });
    }

    // Refresh inspector if link selected
    if (this.selectedLinkId && this.currentLinkStates[this.selectedLinkId]) {
      this.renderInspector(this.currentLinkStates[this.selectedLinkId]);
    }
  },

  focusLink(linkId) {
    this.selectLink(linkId);

    // Zoom to link feature
    if (this.geojsonLayer) {
      this.geojsonLayer.eachLayer(layer => {
        if (layer.feature && layer.feature.properties.link_id === linkId) {
          const bounds = layer.getBounds();
          this.map.fitBounds(bounds, { maxZoom: 16, padding: [80, 80] });
        }
      });
    }
  },

  selectLink(linkId) {
    this.selectedLinkId = linkId;

    if (this.geojsonLayer) {
      this.geojsonLayer.setStyle((feature) => {
        const lid = feature.properties.link_id;
        const color = this.getColorForLink(lid);
        const isSelected = (lid === this.selectedLinkId);

        return {
          color: isSelected ? "#38bdf8" : color,
          weight: isSelected ? 6 : 4,
          opacity: isSelected ? 1.0 : 0.85
        };
      });
    }

    const linkState = this.currentLinkStates[linkId] || { link_id: linkId };
    this.renderInspector(linkState);
  },

  renderInspector(st) {
    const lidEl = document.getElementById("insp-lid");
    const nameEl = document.getElementById("insp-name");
    const losEl = document.getElementById("insp-los");
    const bodyEl = document.getElementById("insp-body");

    if (!bodyEl) return;

    lidEl.textContent = st.link_id || "--";
    nameEl.textContent = st.name || `Link ${st.link_id}`;

    const los = st.level_of_service || "A";
    losEl.textContent = `LOS ${los}`;
    losEl.className = `split-los-pill los-${los.toLowerCase()}`;

    bodyEl.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:12px;">
        <div style="background:#080d1a; padding:12px; border-radius:8px; border:1px solid var(--border-color);">
          <div style="display:flex; justify-content:space-between; font-size:0.85rem; margin-bottom:6px;">
            <span>Current Speed:</span>
            <strong style="font-family:var(--font-mono); color:${st.speed_kph < 20 ? '#ef4444' : '#10b981'};">${st.speed_kph || '--'} km/h</strong>
          </div>
          <div style="display:flex; justify-content:space-between; font-size:0.85rem; margin-bottom:6px;">
            <span>Historical Baseline:</span>
            <span style="font-family:var(--font-mono); color:#94a3b8;">${st.baseline_speed_kph || '--'} km/h</span>
          </div>
          <div style="display:flex; justify-content:space-between; font-size:0.85rem; margin-bottom:6px;">
            <span>Flow Throughput:</span>
            <span style="font-family:var(--font-mono); color:#fff;">${st.flow_vph || '--'} veh / hr</span>
          </div>
          <div style="display:flex; justify-content:space-between; font-size:0.85rem; margin-bottom:6px;">
            <span>Occupancy / Density:</span>
            <span style="font-family:var(--font-mono); color:#fff;">${st.occupancy_pct || '--'}% (${st.density_veh_km_lane || '--'} v/km/ln)</span>
          </div>
          <div style="display:flex; justify-content:space-between; font-size:0.85rem;">
            <span>Volume / Capacity:</span>
            <strong style="font-family:var(--font-mono); color:${st.vc_ratio > 0.9 ? '#ef4444' : '#38bdf8'};">${st.vc_ratio || '--'}</strong>
          </div>
        </div>

        <!-- Telemetry Source & Pipeline Hygiene -->
        <div style="background:#080d1a; padding:12px; border-radius:8px; border:1px solid var(--border-color); font-size:0.8rem;">
          <div style="font-weight:700; color:#94a3b8; margin-bottom:6px;">DATA HYGIENE & SENSORS</div>
          <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
            <span>Source Tier:</span>
            <span style="font-weight:700; color:#38bdf8;">${st.imputation_tier || 'direct_sensor'}</span>
          </div>
          <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
            <span>Imputed Gap:</span>
            <span>${st.is_imputed ? '<span style="color:#fbbf24;">True (Spatial/GT)</span>' : '<span style="color:#10b981;">False (Live Sensor)</span>'}</span>
          </div>
          <div style="display:flex; justify-content:space-between;">
            <span>Severity Score:</span>
            <strong style="color:${st.severity_score >= 70 ? '#ef4444' : '#38bdf8'};">${st.severity_score || 0} / 100</strong>
          </div>
        </div>

        <button class="btn btn-sm btn-outline" style="width:100%; justify-content:center;" onclick="App.switchView('corridor-timeline')">
          <i class="fa-solid fa-timeline"></i> View in Corridor Timeline Strip
        </button>
      </div>
    `;
  }
};

window.SecondaryMap = SecondaryMap;
