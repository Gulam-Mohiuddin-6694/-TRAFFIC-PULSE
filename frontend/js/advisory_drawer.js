/**
 * Traffic Pulse - View 4: Operational Advisory Drawer
 * Operational suggestions with attached evidence:
 * "Divert to Route B - triggered by accident on Link 42, model predicts 22 min saved, confidence 78%"
 * Interactive Approve/Reject buttons for human-in-the-loop traffic engineering.
 */

const AdvisoryDrawer = {
  render(advisoriesList) {
    const container = document.getElementById("advisories-container");
    if (!container) return;

    if (!advisoriesList || advisoriesList.length === 0) {
      container.innerHTML = `
        <div class="card empty-card" style="grid-column: 1 / -1; text-align: center; padding: 40px;">
          <i class="fa-solid fa-check-double" style="font-size: 2rem; color: #10b981; margin-bottom: 12px; display: block;"></i>
          <h3 style="font-weight: 700;">No Operational Interventions Required</h3>
          <p class="text-muted" style="margin-top: 6px;">Current network flows and signals are operating within optimal capacity bands.</p>
        </div>
      `;
      return;
    }

    let html = "";
    advisoriesList.forEach(adv => {
      const ev = adv.evidence || {};
      const isPending = adv.status === "PENDING";
      const isApproved = adv.status === "APPROVED";
      const isRejected = adv.status === "REJECTED";

      const statusBadge = isApproved ?
        '<span style="background:rgba(16,185,129,0.2); color:#34d399; padding:2px 8px; border-radius:4px; font-weight:800; font-size:0.75rem;"><i class="fa-solid fa-circle-check"></i> APPROVED</span>' :
        (isRejected ?
          '<span style="background:rgba(239,68,68,0.2); color:#f87171; padding:2px 8px; border-radius:4px; font-weight:800; font-size:0.75rem;"><i class="fa-solid fa-circle-xmark"></i> REJECTED</span>' :
          '<span style="background:rgba(245,158,11,0.2); color:#fbbf24; padding:2px 8px; border-radius:4px; font-weight:800; font-size:0.75rem;"><i class="fa-solid fa-clock"></i> PENDING APPROVAL</span>'
        );

      const routeString = ev.alternate_route_nodes ? ev.alternate_route_nodes.join(" → ") : "Dynamic signal coordination";

      html += `
        <div class="advisory-card" data-adv-id="${adv.advisory_id}" style="${isApproved ? 'border-left-color: #10b981;' : (isRejected ? 'border-left-color: #64748b; opacity: 0.75;' : '')}">
          <div class="adv-header">
            <div>
              <span class="text-muted" style="font-family: var(--font-mono); font-size: 0.72rem;">${adv.advisory_id}</span>
              <h3 style="font-size: 1.15rem; font-weight: 800; color: #fff; margin-top: 2px;">
                ${adv.title}
              </h3>
            </div>
            <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
              <span class="adv-delay-saved">
                <i class="fa-solid fa-stopwatch"></i> ${ev.delay_saved_min || 15} min saved
              </span>
              ${statusBadge}
            </div>
          </div>

          <div style="font-size: 0.88rem; color: #e2e8f0; line-height: 1.4;">
            <strong>Advisory:</strong> ${adv.summary}
          </div>

          <!-- Attached Evidence Box -->
          <div class="adv-evidence-box">
            <div><strong style="color: #38bdf8;">Trigger Evidence:</strong> ${ev.trigger || 'Telemetry threshold exceeded'}</div>
            <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-top: 2px;">
              <span>Model Confidence: <strong style="color: #38bdf8;">${ev.confidence_pct || 80}%</strong></span>
              ${ev.capacity_headroom_pct ? `<span>Alternate Route Headroom: <strong style="color: #34d399;">${ev.capacity_headroom_pct}% spare</strong></span>` : ''}
              ${ev.green_adjustment_s ? `<span>Phase Extension: <strong style="color: #fbbf24;">+${ev.green_adjustment_s}s Green</strong></span>` : ''}
            </div>
            ${ev.alternate_route_nodes ? `
              <div style="margin-top: 4px; font-family: var(--font-mono); font-size: 0.75rem; color: #94a3b8;">
                <i class="fa-solid fa-arrows-split-up-and-left text-teal"></i> Path: ${routeString}
              </div>
            ` : ''}
          </div>

          <!-- Human-in-the-Loop Actions -->
          <div class="adv-actions-row">
            <span class="text-muted" style="font-size: 0.75rem;">
              Generated: ${adv.generated_at}
            </span>
            <div class="btn-group">
              ${isPending ? `
                <button class="btn btn-sm btn-reject btn-action-reject" data-adv-id="${adv.advisory_id}">
                  <i class="fa-solid fa-xmark"></i> Reject
                </button>
                <button class="btn btn-sm btn-approve btn-action-approve" data-adv-id="${adv.advisory_id}">
                  <i class="fa-solid fa-check"></i> Approve Advisory
                </button>
              ` : `
                <span class="text-muted" style="font-size: 0.75rem; font-style: italic;">
                  Decision recorded (${adv.status.toLowerCase()})
                </span>
              `}
            </div>
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
    this.bindActionButtons();
  },

  bindActionButtons() {
    document.querySelectorAll(".btn-action-approve").forEach(btn => {
      btn.addEventListener("click", async () => {
        const advId = btn.getAttribute("data-adv-id");
        await this.submitDecision(advId, "APPROVE");
      });
    });

    document.querySelectorAll(".btn-action-reject").forEach(btn => {
      btn.addEventListener("click", async () => {
        const advId = btn.getAttribute("data-adv-id");
        await this.submitDecision(advId, "REJECT");
      });
    });
  },

  async submitDecision(advId, action) {
    try {
      const res = await fetch(`/api/advisory/${advId}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action })
      });
      const data = await res.json();
      App.showToast(`Advisory ${advId} ${action.toLowerCase()}d by operator`, action === "APPROVE" ? "success" : "warning");
      App.fetchCurrentState();
    } catch (err) {
      console.error("Failed to submit advisory action:", err);
    }
  }
};

window.AdvisoryDrawer = AdvisoryDrawer;
