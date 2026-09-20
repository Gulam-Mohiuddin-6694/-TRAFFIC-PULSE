/**
 * Traffic Pulse - View 3: Incident Evidence Panel
 * Structured cards with evidence: location, type + confidence, detected-at time,
 * triggering signals (speed drop sparkline, occupancy spike), nearby cameras,
 * and recommended action buttons.
 */

const IncidentPanel = {
  render(incidentsList) {
    const container = document.getElementById("incidents-container");
    if (!container) return;

    if (!incidentsList || incidentsList.length === 0) {
      container.innerHTML = `
        <div class="card empty-card" style="grid-column: 1 / -1; text-align: center; padding: 40px;">
          <i class="fa-solid fa-shield-check" style="font-size: 2rem; color: #10b981; margin-bottom: 12px; display: block;"></i>
          <h3 style="font-weight: 700;">No Critical Incidents Detected</h3>
          <p class="text-muted" style="margin-top: 6px;">All link speeds, occupancy levels, and shockwave gradients are within expected baseline parameters.</p>
        </div>
      `;
      return;
    }

    let html = "";
    incidentsList.forEach(inc => {
      const isLowConf = inc.is_low_confidence;
      const typeClass = inc.type === "collision" ? "card-severe" : (isLowConf ? "card-low-conf" : "card-workzone");
      const badgeClass = inc.type === "collision" ? "badge-collision" : (isLowConf ? "badge-abnormal" : "badge-workzone");
      const icon = inc.type === "collision" ? "fa-car-burst" : (isLowConf ? "fa-triangle-exclamation" : (inc.type === "work_zone" ? "fa-person-digging" : "fa-truck-tow"));

      const tr = inc.triggering_signals || {};
      const ctx = inc.context || {};

      // Draw mini SVG sparkline
      const sparklinePoints = (tr.speed_sparkline || [tr.current_speed_kph || 20]).map((v, i, arr) => {
        const x = (i / Math.max(1, arr.length - 1)) * 140;
        const maxV = 70.0;
        const y = 35 - (Math.min(maxV, v) / maxV) * 30;
        return `${x},${y}`;
      }).join(" ");

      html += `
        <div class="incident-card ${typeClass}">
          <div class="inc-header">
            <div>
              <div class="inc-type-badge ${badgeClass}">
                <i class="fa-solid ${icon}"></i>
                <span>${inc.type_label}</span>
                <span style="font-weight: 800; font-family: var(--font-mono); margin-left: 4px;">(${inc.confidence.toFixed(0)}% conf)</span>
                ${isLowConf ? '<span style="font-size:0.6rem; background:rgba(0,0,0,0.4); padding:1px 4px; border-radius:3px;">UNCERTAIN</span>' : ''}
              </div>
              <h3 style="font-size: 1.15rem; font-weight: 800; margin-top: 8px; color: #fff;">
                ${inc.link_id} — ${inc.corridor_name}
              </h3>
              <span class="text-muted" style="font-size: 0.76rem; font-family: var(--font-mono);">
                Coordinates: ${inc.lat.toFixed(4)}, ${inc.lon.toFixed(4)} | Road Class: ${inc.road_class.toUpperCase()}
              </span>
            </div>
            <div style="text-align: right;">
              <span class="text-muted" style="font-size: 0.72rem; display: block;">DETECTED AT</span>
              <span style="font-family: var(--font-mono); font-size: 0.84rem; font-weight: 700; color: #38bdf8;">${inc.detected_at.split(' ')[1]}</span>
            </div>
          </div>

          <!-- Triggering Telemetry Signals -->
          <div class="inc-signals-grid">
            <div class="signal-item">
              <span class="signal-label">SPEED COLLAPSE</span>
              <span class="signal-val text-crimson">${tr.current_speed_kph ? tr.current_speed_kph.toFixed(1) : '--'} km/h</span>
              <span class="text-muted" style="font-size: 0.68rem;">Drop: -${tr.speed_drop_pct ? tr.speed_drop_pct.toFixed(0) : '--'}%</span>
            </div>

            <div class="signal-item">
              <span class="signal-label">OCCUPANCY SPIKE</span>
              <span class="signal-val text-amber">${tr.occupancy_pct ? tr.occupancy_pct.toFixed(1) : '--'}%</span>
              <span class="text-muted" style="font-size: 0.68rem;">Shockwave: ${tr.shockwave_ratio || 1.0}x</span>
            </div>

            <div class="signal-item">
              <span class="signal-label">ML ANOMALY SCORE</span>
              <span class="signal-val" style="color: #c084fc;">${tr.anomaly_score ? tr.anomaly_score.toFixed(1) : 80} / 100</span>
              <span class="text-muted" style="font-size: 0.68rem;">Isolation Forest</span>
            </div>
          </div>

          <!-- Speed History Sparkline & CCTV Sensor Context -->
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; align-items: center;">
            <div style="background: #080d1a; border: 1px solid var(--border-color); border-radius: 6px; padding: 8px 12px;">
              <div style="display: flex; justify-content: space-between; font-size: 0.68rem; color: var(--text-muted); margin-bottom: 4px;">
                <span>SPEED DROP PROFILE</span>
                <span class="text-crimson">${tr.current_speed_kph ? tr.current_speed_kph.toFixed(1) : '--'} km/h</span>
              </div>
              <svg width="140" height="38" style="overflow: visible;">
                <polyline fill="none" stroke="#ef4444" stroke-width="2.5" stroke-linecap="round" points="${sparklinePoints}" />
              </svg>
            </div>

            <!-- Simulated CCTV Feed Preview -->
            <div class="cctv-preview">
              <div class="cctv-overlay"><i class="fa-solid fa-video"></i> ${ctx.sensor_id || 'CCTV-CAM1'} [LIVE]</div>
              <div style="text-align: center; color: #64748b; font-size: 0.72rem;">
                <i class="fa-solid fa-camera-viewfinder" style="font-size: 1.4rem; color: #334155; margin-bottom: 4px; display: block;"></i>
                Telemetry Verified (Weather: ${ctx.weather_condition || 'Clear'})
              </div>
            </div>
          </div>

          <!-- Action & Advisory Trigger -->
          <div style="display: flex; align-items: center; justify-content: space-between; border-top: 1px solid var(--border-color); padding-top: 12px; margin-top: 4px;">
            <div style="font-size: 0.8rem; color: var(--text-secondary); max-width: 70%;">
              <i class="fa-solid fa-lightbulb text-amber"></i> ${inc.recommended_action}
            </div>
            <button class="btn btn-sm btn-teal btn-act-advisory" data-link-id="${inc.link_id}" data-action-type="${inc.action_type}">
              <i class="fa-solid fa-arrow-right"></i> Act Now
            </button>
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
    this.bindActionButtons();
  },

  bindActionButtons() {
    document.querySelectorAll(".btn-act-advisory").forEach(btn => {
      btn.addEventListener("click", () => {
        const lid = btn.getAttribute("data-link-id");
        App.switchView("advisory-drawer");
        App.showToast(`Switched to Operational Advisories for Link ${lid}`, "info");
      });
    });
  }
};

window.IncidentPanel = IncidentPanel;
