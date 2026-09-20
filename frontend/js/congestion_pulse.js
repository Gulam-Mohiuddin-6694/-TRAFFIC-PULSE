/**
 * Traffic Pulse - View 1: Congestion Pulse (Home View)
 * Ranked top 10 critical bottlenecks with severity bars, speed vs baseline %,
 * trend arrows, multi-horizon forecasts (+15/+30/+45/+60m), and quick actions.
 */

const CongestionPulse = {
  render(top10List) {
    const tbody = document.getElementById("pulse-tbody");
    if (!tbody) return;

    if (!top10List || top10List.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center py-4 text-muted">No active bottlenecks detected. Network is operating smoothly.</td></tr>';
      return;
    }

    let html = "";
    top10List.forEach((item, index) => {
      const rank = index + 1;
      const rankClass = rank === 1 ? "rank-1" : (rank === 2 ? "rank-2" : (rank === 3 ? "rank-3" : ""));

      // Road class badge
      const rcClass = `rc-${item.road_class || "secondary"}`;

      // Severity bar color
      let barFillClass = "fill-low";
      if (item.severity_score >= 70) barFillClass = "fill-critical";
      else if (item.severity_score >= 45) barFillClass = "fill-high";
      else if (item.severity_score >= 25) barFillClass = "fill-moderate";

      // Trend arrow
      let trendClass = "trend-steady";
      if (item.trend === "worsening") trendClass = "trend-worsening";
      else if (item.trend === "improving") trendClass = "trend-improving";

      // Forecast pills
      const fc = item.forecast || {};
      const f15 = fc["+15m"] !== undefined ? fc["+15m"] : "--";
      const f30 = fc["+30m"] !== undefined ? fc["+30m"] : "--";
      const f45 = fc["+45m"] !== undefined ? fc["+45m"] : "--";
      const f60 = fc["+60m"] !== undefined ? fc["+60m"] : "--";

      html += `
        <tr data-link-id="${item.link_id}">
          <td>
            <div class="rank-badge ${rankClass}">#${rank}</div>
          </td>
          <td>
            <span class="link-title">${item.link_id}</span>
            <span class="link-meta">${item.name}</span>
          </td>
          <td>
            <span class="road-class-pill ${rcClass}">${item.road_class}</span>
          </td>
          <td>
            <div class="severity-cell">
              <div class="severity-text-row">
                <span class="${item.severity_score >= 70 ? 'text-crimson' : (item.severity_score >= 45 ? 'text-amber' : 'text-blue')}">
                  ${item.severity_level.toUpperCase()}
                </span>
                <span>${item.severity_score.toFixed(1)} / 100</span>
              </div>
              <div class="severity-bar-bg">
                <div class="severity-bar-fill ${barFillClass}" style="width: ${Math.min(100, item.severity_score)}%;"></div>
              </div>
            </div>
          </td>
          <td>
            <div class="speed-cell">
              <strong>${item.speed_kph.toFixed(1)}</strong>
              <span class="text-muted">/ ${item.baseline_speed_kph.toFixed(1)} km/h</span>
              <span class="speed-drop-tag">-${item.speed_drop_pct.toFixed(0)}%</span>
            </div>
          </td>
          <td style="text-align: center;">
            <span class="trend-arrow ${trendClass}" title="${item.trend}">
              ${item.trend_symbol}
            </span>
          </td>
          <td>
            <div class="forecast-pills">
              <div class="f-pill"><span class="f-horizon">+15m</span><span class="f-val">${f15}</span></div>
              <div class="f-pill"><span class="f-horizon">+30m</span><span class="f-val">${f30}</span></div>
              <div class="f-pill"><span class="f-horizon">+45m</span><span class="f-val">${f45}</span></div>
              <div class="f-pill"><span class="f-horizon">+60m</span><span class="f-val">${f60}</span></div>
            </div>
          </td>
          <td>
            <span style="font-family: var(--font-mono); font-weight: 700; color: #38bdf8;">
              ${item.confidence ? item.confidence.toFixed(0) : 85}%
            </span>
          </td>
          <td style="text-align: right;">
            <div class="btn-group" style="justify-content: flex-end;">
              <button class="btn btn-sm btn-outline btn-quick-corridor" data-link-id="${item.link_id}" data-name="${item.name}" title="View Corridor Timeline Strip">
                <i class="fa-solid fa-timeline"></i> Strip
              </button>
              <button class="btn btn-sm btn-outline btn-quick-map" data-link-id="${item.link_id}" title="Drill-down on Map">
                <i class="fa-solid fa-crosshairs"></i>
              </button>
            </div>
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = html;
    this.bindRowActions();
  },

  bindRowActions() {
    document.querySelectorAll(".btn-quick-corridor").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const name = btn.getAttribute("data-name") || "";
        // Match corridor
        let targetCorridor = "EW-TRU-EB";
        if (name.includes("EW-TRU")) targetCorridor = "EW-TRU-EB";
        else if (name.includes("EW-PRI")) targetCorridor = "EW-PRI-EB";
        else if (name.includes("EW-SEC")) targetCorridor = "EW-SEC-EB";
        else if (name.includes("NS-TRU")) targetCorridor = "NS-TRU-NB";
        else if (name.includes("NS-PRI")) targetCorridor = "NS-PRI-NB";

        const select = document.getElementById("corridor-select");
        if (select) select.value = targetCorridor;

        App.switchView("corridor-timeline");
        App.showToast(`Switched to Corridor Timeline: ${targetCorridor}`, "info");
      });
    });

    document.querySelectorAll(".btn-quick-map").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const lid = btn.getAttribute("data-link-id");
        App.switchView("map-layer");
        if (window.SecondaryMap) {
          window.SecondaryMap.focusLink(lid);
        }
      });
    });

    // Clicking row opens map drilldown
    document.querySelectorAll("#pulse-tbody tr").forEach(row => {
      row.addEventListener("click", () => {
        const lid = row.getAttribute("data-link-id");
        if (lid) {
          App.switchView("map-layer");
          if (window.SecondaryMap) {
            window.SecondaryMap.focusLink(lid);
          }
        }
      });
    });
  }
};

window.CongestionPulse = CongestionPulse;
