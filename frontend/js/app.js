/**
 * Traffic Pulse - Master Application Controller
 * Manages SSE live streaming, playback clock controls, view switching, and state dispatch.
 */

const App = {
  state: {
    currentTimestamp: "2024-01-01 16:00:00",
    isPlaying: false,
    playbackSpeed: 1.0,
    networkSummary: {},
    congestionPulseTop10: [],
    activeIncidents: [],
    activeAdvisories: [],
    allLinks: [],
    networkMetadata: null
  },

  sseSource: null,

  init() {
    this.bindEvents();
    this.loadNetworkMetadata();
    this.fetchCurrentState();
    this.initSSE();

    // Auto-refresh state periodically if not connected to SSE
    setInterval(() => {
      if (!this.sseSource || this.sseSource.readyState !== EventSource.OPEN) {
        if (this.state.isPlaying) {
          this.playbackAction("step");
        }
      }
    }, 4000);
  },

  bindEvents() {
    // View Tab Navigation
    document.querySelectorAll(".tab-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const viewId = btn.getAttribute("data-view");
        this.switchView(viewId);
      });
    });

    // Playback Controls
    document.getElementById("btn-play-pause").addEventListener("click", () => {
      const action = this.state.isPlaying ? "pause" : "play";
      this.playbackAction(action);
    });

    document.getElementById("btn-step").addEventListener("click", () => {
      this.playbackAction("step");
    });

    document.getElementById("select-speed").addEventListener("change", (e) => {
      const speed = parseFloat(e.target.value);
      this.playbackAction("speed", { speed });
    });

    // Jump to Major Incident (Collision on L00041 at 16:45)
    document.getElementById("btn-jump-incident").addEventListener("click", () => {
      this.playbackAction("jump", { timestamp: "2024-01-01 16:45:00" });
      this.showToast("Jumped to Major Collision Incident window (16:45:00)", "warning");
      this.switchView("congestion-pulse");
    });
  },

  switchView(viewId) {
    // Update tab buttons
    document.querySelectorAll(".tab-btn").forEach(b => {
      b.classList.toggle("active", b.getAttribute("data-view") === viewId);
    });

    // Update view sections
    document.querySelectorAll(".view-section").forEach(sec => {
      sec.classList.toggle("active", sec.id === `view-${viewId}`);
    });

    // Trigger view-specific re-renders
    if (viewId === "corridor-timeline" && window.CorridorStrip) {
      window.CorridorStrip.fetchAndRender();
    } else if (viewId === "map-layer" && window.SecondaryMap) {
      window.SecondaryMap.invalidateSize();
    } else if (viewId === "simulator" && window.Simulator) {
      window.Simulator.fetchProjectSimulation();
    }
  },

  async loadNetworkMetadata() {
    try {
      const res = await fetch("/api/network");
      const data = await res.json();
      this.state.networkMetadata = data;
      if (window.SecondaryMap) {
        window.SecondaryMap.initMap(data.geojson);
      }
    } catch (err) {
      console.error("Failed to load network metadata:", err);
    }
  },

  async fetchCurrentState() {
    try {
      const res = await fetch("/api/current_state");
      const data = await res.json();
      this.updateState(data);
    } catch (err) {
      console.error("Failed to fetch current state:", err);
    }
  },

  initSSE() {
    try {
      this.sseSource = new EventSource("/api/stream");
      const badge = document.getElementById("ticker-stream-badge");

      this.sseSource.onopen = () => {
        if (badge) badge.innerHTML = '<i class="fa-solid fa-circle pulse-dot"></i> LIVE SSE';
      };

      this.sseSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.updateState(data);
        } catch (e) {
          console.error("SSE parse error:", e);
        }
      };

      this.sseSource.onerror = () => {
        if (badge) badge.innerHTML = '<i class="fa-solid fa-circle text-amber"></i> POLLING';
      };
    } catch (err) {
      console.warn("SSE not supported, using polling fallback.");
    }
  },

  updateState(data) {
    if (data.timestamp) {
      this.state.currentTimestamp = data.timestamp;
      document.getElementById("sim-clock").textContent = data.timestamp;
    }
    if (data.is_playing !== undefined) {
      this.state.isPlaying = data.is_playing;
      const playIcon = document.querySelector("#btn-play-pause i");
      if (playIcon) {
        playIcon.className = this.state.isPlaying ? "fa-solid fa-pause" : "fa-solid fa-play";
      }
    }

    if (data.network_summary) {
      this.state.networkSummary = data.network_summary;
      document.getElementById("ticker-avg-speed").textContent = `${data.network_summary.avg_speed_kph || "--"} km/h`;
      document.getElementById("ticker-critical-count").textContent = `${data.network_summary.critical_links_count || 0} Links`;
    }

    if (data.active_incidents) {
      this.state.activeIncidents = data.active_incidents;
      document.getElementById("ticker-incident-count").textContent = `${data.active_incidents.length} Detected`;
      document.getElementById("tab-inc-count").textContent = data.active_incidents.length;
      document.getElementById("incident-counter-badge").textContent = `${data.active_incidents.length} Active Suspected Incidents`;
      if (window.IncidentPanel) window.IncidentPanel.render(data.active_incidents);
    }

    if (data.active_advisories) {
      this.state.activeAdvisories = data.active_advisories;
      const pendingCount = data.active_advisories.filter(a => a.status === "PENDING").length;
      document.getElementById("tab-adv-count").textContent = pendingCount;
      document.getElementById("advisories-pending-count").textContent = `${pendingCount} Pending Approvals`;
      if (window.AdvisoryDrawer) window.AdvisoryDrawer.render(data.active_advisories);
    }

    if (data.congestion_pulse_top10) {
      this.state.congestionPulseTop10 = data.congestion_pulse_top10;
      if (window.CongestionPulse) window.CongestionPulse.render(data.congestion_pulse_top10);
    }

    if (data.all_links) {
      this.state.allLinks = data.all_links;
      if (window.SecondaryMap) window.SecondaryMap.updateLinkStates(data.all_links);
    }

    // Refresh active corridor view if visible
    const activeSec = document.querySelector(".view-section.active");
    if (activeSec && activeSec.id === "view-corridor-timeline" && window.CorridorStrip) {
      window.CorridorStrip.fetchAndRender();
    }
  },

  async playbackAction(action, payload = {}) {
    try {
      const res = await fetch("/api/playback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...payload })
      });
      const data = await res.json();
      this.fetchCurrentState();
    } catch (err) {
      console.error("Playback command failed:", err);
    }
  },

  showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    const icon = type === "warning" ? "fa-triangle-exclamation text-amber" : (type === "success" ? "fa-circle-check text-green" : "fa-circle-info text-blue");
    toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
};

document.addEventListener("DOMContentLoaded", () => {
  App.init();
});
