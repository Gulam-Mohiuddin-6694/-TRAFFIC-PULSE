/**
 * Traffic Pulse - View 5: Before/After Infrastructure Simulator
 * Evaluates recurring bottleneck relief proposals with split-view comparison
 * and interactive 24-hour diurnal replay time-slider.
 */

const Simulator = {
  currentProjectData: null,
  timelineSteps: [],

  init() {
    const projSelect = document.getElementById("project-select");
    if (projSelect) {
      projSelect.addEventListener("change", () => {
        this.fetchProjectSimulation();
      });
    }

    const slider = document.getElementById("time-slider");
    if (slider) {
      slider.addEventListener("input", (e) => {
        const stepIdx = parseInt(e.target.value, 10);
        this.renderStep(stepIdx);
      });
    }

    this.fetchProjectSimulation();
  },

  async fetchProjectSimulation() {
    const projSelect = document.getElementById("project-select");
    const projId = projSelect ? projSelect.value : "PROJ-LANE-EW-TRU";

    try {
      const res = await fetch(`/api/infrastructure/simulate?project_id=${projId}`);
      const data = await res.json();
      this.currentProjectData = data;
      this.timelineSteps = data.replay_timeline_24h || [];

      this.renderExecutiveSummary(data);

      const slider = document.getElementById("time-slider");
      const currentStep = slider ? parseInt(slider.value, 10) : 51;
      this.renderStep(currentStep);
    } catch (err) {
      console.error("Failed to load infrastructure simulation:", err);
    }
  },

  renderExecutiveSummary(data) {
    const proj = data.project || {};
    const sum = data.metrics_summary || {};

    // Project descriptions & badges
    document.getElementById("proj-title").textContent = proj.title || "Infrastructure Proposal";
    document.getElementById("proj-desc").textContent = proj.description || "";
    document.getElementById("proj-cost").innerHTML = `<i class="fa-solid fa-coins"></i> ${proj.cost_estimate || '$3M'}`;
    document.getElementById("proj-duration").innerHTML = `<i class="fa-solid fa-calendar-day"></i> ${proj.construction_duration || '3 months'}`;
    document.getElementById("proj-economic").innerHTML = `<i class="fa-solid fa-arrow-trend-up"></i> ${sum.annual_economic_benefit || '$0.5M/yr'} Benefit`;

    // KPI comparison
    document.getElementById("kpi-speed-before").textContent = `${sum.avg_speed_before_kph || '--'} km/h`;
    document.getElementById("kpi-speed-after").textContent = `${sum.avg_speed_after_kph || '--'} km/h`;
    document.getElementById("kpi-speed-delta").textContent = `+${sum.speed_improvement_pct || 0}% Speed Gain`;

    document.getElementById("kpi-queue-before").textContent = `${sum.peak_queue_before_veh || '--'} veh`;
    document.getElementById("kpi-queue-after").textContent = `${sum.peak_queue_after_veh || '--'} veh`;
    document.getElementById("kpi-queue-delta").textContent = `-${sum.queue_reduction_pct || 0}% Queue Dissipation`;

    document.getElementById("kpi-delay-saved").textContent = `${sum.daily_delay_hours_saved || '--'} hrs / day`;
    document.getElementById("kpi-los-shift").textContent = sum.peak_los_improvement || "LOS F → LOS B";
  },

  renderStep(stepIdx) {
    if (!this.timelineSteps || this.timelineSteps.length === 0) return;
    const clampedIdx = Math.max(0, Math.min(this.timelineSteps.length - 1, stepIdx));
    const step = this.timelineSteps[clampedIdx];

    // Scrubber label
    let periodTag = "Off-Peak";
    if (step.minute >= 420 && step.minute <= 570) periodTag = "AM Peak Period";
    else if (step.minute >= 990 && step.minute <= 1140) periodTag = "PM Peak Period";
    else if (step.minute >= 720 && step.minute <= 840) periodTag = "Midday Demand";

    document.getElementById("scrubber-time-val").textContent = `${step.time} (${periodTag}) — Demand: ${step.demand_vph} vph`;

    const base = step.baseline || {};
    const post = step.post_modification || {};

    // Baseline elements
    document.getElementById("split-base-speed").textContent = `${base.speed_kph} km/h`;
    document.getElementById("split-base-vc").textContent = `${base.vc_ratio} (v/c)`;
    document.getElementById("split-base-queue").textContent = `${base.queue_veh} vehicles`;
    document.getElementById("split-base-tt").textContent = `${base.travel_time_s} seconds`;

    const baseLosPill = document.getElementById("split-base-los");
    baseLosPill.textContent = `LOS ${base.los}`;
    baseLosPill.className = `split-los-pill los-${base.los.toLowerCase()}`;

    const maxQ = 100.0;
    const baseQBar = document.getElementById("split-base-queue-bar");
    if (baseQBar) baseQBar.style.width = `${Math.min(100, (base.queue_veh / maxQ) * 100)}%`;

    // Post-modification elements
    document.getElementById("split-post-speed").textContent = `${post.speed_kph} km/h`;
    document.getElementById("split-post-vc").textContent = `${post.vc_ratio} (v/c)`;
    document.getElementById("split-post-queue").textContent = `${post.queue_veh} vehicles`;
    document.getElementById("split-post-tt").textContent = `${post.travel_time_s} seconds`;

    const postLosPill = document.getElementById("split-post-los");
    postLosPill.textContent = `LOS ${post.los}`;
    postLosPill.className = `split-los-pill los-${post.los.toLowerCase()}`;

    const postQBar = document.getElementById("split-post-queue-bar");
    if (postQBar) postQBar.style.width = `${Math.min(100, (post.queue_veh / maxQ) * 100)}%`;
  }
};

window.Simulator = Simulator;
document.addEventListener("DOMContentLoaded", () => {
  Simulator.init();
});
