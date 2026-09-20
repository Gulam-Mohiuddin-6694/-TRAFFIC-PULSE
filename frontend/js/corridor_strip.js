/**
 * Traffic Pulse - View 2: Corridor Timeline Strip (Space-Time Diagram)
 * Haut-Trajectoire contour: X-axis = distance along corridor (m), Y-axis = time
 * Visualizes shockwave propagation, jam fronts, and incident onset.
 */

const CorridorStrip = {
  data: null,
  canvas: null,
  ctx: null,
  hoverCell: null,

  init() {
    this.canvas = document.getElementById("space-time-canvas");
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");

    // Corridor dropdown selector event
    const select = document.getElementById("corridor-select");
    if (select) {
      select.addEventListener("change", () => {
        this.fetchAndRender();
      });
    }

    // Hover tooltip interactions
    this.canvas.addEventListener("mousemove", (e) => this.handleMouseMove(e));
    this.canvas.addEventListener("mouseleave", () => this.handleMouseLeave());

    this.fetchAndRender();
  },

  async fetchAndRender() {
    const select = document.getElementById("corridor-select");
    const corridorId = select ? select.value : "EW-TRU-EB";

    try {
      const res = await fetch(`/api/corridor_timeline?corridor=${corridorId}`);
      const json = await res.json();
      this.data = json;

      // Update corridor summary info
      const stats = document.getElementById("corridor-summary-stats");
      if (stats && json.total_length_m) {
        stats.textContent = `${json.label} | Length: ${(json.total_length_m / 1000).toFixed(2)} km | ${json.links.length} Links`;
      }

      this.draw();
    } catch (err) {
      console.error("Failed to fetch corridor timeline:", err);
    }
  },

  getColorForSpeed(speed, freeFlow) {
    const ratio = freeFlow > 0 ? speed / freeFlow : 1.0;
    if (speed < 12.0 || ratio < 0.28) {
      return "#ef4444"; // Crimson (Jam / Stop-and-Go)
    } else if (speed < 25.0 || ratio < 0.45) {
      return "#f97316"; // Orange
    } else if (speed < 40.0 || ratio < 0.65) {
      return "#f59e0b"; // Amber
    } else if (speed < 55.0 || ratio < 0.85) {
      return "#34d399"; // Mint
    } else {
      return "#10b981"; // Emerald (Free flow)
    }
  },

  draw() {
    if (!this.data || !this.canvas || !this.ctx) return;

    const ctx = this.ctx;
    const width = this.canvas.width;
    const height = this.canvas.height;

    ctx.clearRect(0, 0, width, height);

    const totalDist = this.data.total_length_m || 2000.0;
    const rows = this.data.timeline_rows || [];
    const numRows = rows.length;
    if (numRows === 0) return;

    // Layout margins
    const marginLeft = 130;
    const marginRight = 30;
    const marginTop = 35;
    const marginBottom = 45;

    const plotWidth = width - marginLeft - marginRight;
    const plotHeight = height - marginTop - marginBottom;
    const rowHeight = plotHeight / numRows;

    // 1. Draw Space-Time Grid Cells
    rows.forEach((row, rIdx) => {
      const y = marginTop + rIdx * rowHeight;
      const cells = row.cells || [];

      cells.forEach(cell => {
        const xStart = marginLeft + (cell.start_m / totalDist) * plotWidth;
        const xEnd = marginLeft + (cell.end_m / totalDist) * plotWidth;
        const cellWidth = Math.max(2, xEnd - xStart);

        const linfo = this.data.links.find(l => l.link_id === cell.link_id) || {};
        const ff = linfo.free_flow_speed_kph || 60.0;
        const color = this.getColorForSpeed(cell.speed_kph, ff);

        ctx.fillStyle = color;
        ctx.fillRect(xStart, y, cellWidth, rowHeight);

        // Cell border
        ctx.strokeStyle = "rgba(0,0,0,0.3)";
        ctx.lineWidth = 0.5;
        ctx.strokeRect(xStart, y, cellWidth, rowHeight);
      });

      // Time labels on Y-axis
      ctx.fillStyle = row.is_now ? "#38bdf8" : (row.is_forecast ? "#94a3b8" : "#64748b");
      ctx.font = row.is_now ? "bold 11px SFMono-Regular, monospace" : "10px SFMono-Regular, monospace";
      ctx.textAlign = "right";
      ctx.fillText(row.time_str, marginLeft - 10, y + rowHeight / 2 + 3);

      // Distinct NOW reference divider line
      if (row.is_now) {
        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.moveTo(marginLeft, y + rowHeight);
        ctx.lineTo(marginLeft + plotWidth, y + rowHeight);
        ctx.stroke();

        // Forecast label
        ctx.fillStyle = "#38bdf8";
        ctx.font = "bold 9px sans-serif";
        ctx.textAlign = "left";
        ctx.fillText("▲ PAST RECENT (60 min) | ▼ MODEL FORECAST (+60 min)", marginLeft + 10, y + rowHeight - 4);
      }
    });

    // 2. Draw Distance Axis on Bottom & Top (Nodes & Intersections)
    const links = this.data.links || [];
    ctx.strokeStyle = "#334155";
    ctx.lineWidth = 1;

    // Bottom Axis Line
    ctx.beginPath();
    ctx.moveTo(marginLeft, height - marginBottom);
    ctx.lineTo(marginLeft + plotWidth, height - marginBottom);
    ctx.stroke();

    links.forEach((l, idx) => {
      const xNode = marginLeft + (l.start_m / totalDist) * plotWidth;

      // Vertical tick mark
      ctx.beginPath();
      ctx.moveTo(xNode, height - marginBottom);
      ctx.lineTo(xNode, height - marginBottom + 6);
      ctx.stroke();

      // Node label
      ctx.fillStyle = "#94a3b8";
      ctx.font = "bold 10px SFMono-Regular, monospace";
      ctx.textAlign = "center";
      ctx.fillText(l.u, xNode, height - marginBottom + 18);

      // Distance in meters
      ctx.fillStyle = "#64748b";
      ctx.font = "9px sans-serif";
      ctx.fillText(`${Math.round(l.start_m)}m`, xNode, height - marginBottom + 30);
    });

    // End node of final link
    if (links.length > 0) {
      const lastLink = links[links.length - 1];
      const xLast = marginLeft + (lastLink.end_m / totalDist) * plotWidth;
      ctx.fillStyle = "#94a3b8";
      ctx.font = "bold 10px SFMono-Regular, monospace";
      ctx.textAlign = "center";
      ctx.fillText(lastLink.v, xLast, height - marginBottom + 18);
      ctx.fillStyle = "#64748b";
      ctx.font = "9px sans-serif";
      ctx.fillText(`${Math.round(lastLink.end_m)}m`, xLast, height - marginBottom + 30);
    }

    // Distance Axis Title
    ctx.fillStyle = "#38bdf8";
    ctx.font = "bold 10px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("DISTANCE ALONG CORRIDOR (meters / nodes)", marginLeft + plotWidth / 2, height - 6);

    // 3. Highlight Shockwave Slopes (Retrograde Deceleration Waves)
    ctx.save();
    ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1.5;

    // Draw representative shockwave propagation trajectory if congestion present
    const hasJam = rows.some(r => r.cells && r.cells.some(c => c.speed_kph < 15.0));
    if (hasJam) {
      const jamRowIdx = rows.findIndex(r => r.cells && r.cells.some(c => c.speed_kph < 15.0));
      if (jamRowIdx >= 0 && jamRowIdx < numRows - 4) {
        const yStart = marginTop + jamRowIdx * rowHeight;
        const xJam = marginLeft + plotWidth * 0.65;
        const yEnd = marginTop + (jamRowIdx + 4) * rowHeight;
        const xProp = marginLeft + plotWidth * 0.45; // Upstream slope

        ctx.beginPath();
        ctx.moveTo(xJam, yStart);
        ctx.lineTo(xProp, yEnd);
        ctx.stroke();

        ctx.fillStyle = "#f87171";
        ctx.font = "italic 9px sans-serif";
        ctx.fillText("Shockwave Front (w = -18 km/h)", xProp - 40, yEnd + 12);
      }
    }
    ctx.restore();
  },

  handleMouseMove(e) {
    if (!this.data || !this.canvas) return;

    const rect = this.canvas.getBoundingClientRect();
    const scaleX = this.canvas.width / rect.width;
    const scaleY = this.canvas.height / rect.height;

    const mouseX = (e.clientX - rect.left) * scaleX;
    const mouseY = (e.clientY - rect.top) * scaleY;

    const marginLeft = 130;
    const marginRight = 30;
    const marginTop = 35;
    const marginBottom = 45;

    const plotWidth = this.canvas.width - marginLeft - marginRight;
    const plotHeight = this.canvas.height - marginTop - marginBottom;
    const rows = this.data.timeline_rows || [];
    const numRows = rows.length;

    if (
      mouseX >= marginLeft && mouseX <= marginLeft + plotWidth &&
      mouseY >= marginTop && mouseY <= marginTop + plotHeight
    ) {
      const rowHeight = plotHeight / numRows;
      const rIdx = Math.floor((mouseY - marginTop) / rowHeight);
      const row = rows[rIdx];

      if (row) {
        const totalDist = this.data.total_length_m || 2000.0;
        const distRatio = (mouseX - marginLeft) / plotWidth;
        const currentMeters = distRatio * totalDist;

        // Find link cell containing currentMeters
        const cell = (row.cells || []).find(c => currentMeters >= c.start_m && currentMeters <= c.end_m) || row.cells[0];

        if (cell) {
          const tooltip = document.getElementById("diagram-tooltip");
          if (tooltip) {
            tooltip.style.display = "block";
            tooltip.style.left = `${e.clientX - rect.left + 15}px`;
            tooltip.style.top = `${e.clientY - rect.top + 15}px`;

            const status = cell.speed_kph < 15.0 ? "<span style='color:#f87171;'>STOP-AND-GO JAM</span>" : (cell.speed_kph < 35.0 ? "<span style='color:#fbbf24;'>CONGESTED</span>" : "<span style='color:#34d399;'>FREE FLOW</span>");

            tooltip.innerHTML = `
              <div style="font-weight:bold; color:#38bdf8; margin-bottom:4px;">${row.time_str} ${row.is_now ? '(NOW)' : ''}</div>
              <div>Link: <strong>${cell.link_id}</strong> (${cell.name})</div>
              <div>Offset: <strong>${Math.round(currentMeters)}m</strong> / ${Math.round(totalDist)}m</div>
              <div>Speed: <strong>${cell.speed_kph} km/h</strong> (${status})</div>
              <div>LOS: <strong>${cell.los}</strong> | Occupancy: <strong>${cell.occupancy_pct}%</strong></div>
            `;
          }
        }
      }
    } else {
      this.handleMouseLeave();
    }
  },

  handleMouseLeave() {
    const tooltip = document.getElementById("diagram-tooltip");
    if (tooltip) tooltip.style.display = "none";
  }
};

window.CorridorStrip = CorridorStrip;
document.addEventListener("DOMContentLoaded", () => {
  CorridorStrip.init();
});
