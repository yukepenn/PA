(function () {
  // Continuous hover-y marker bridge for Dash + Plotly.
  // Throttled to avoid excessive network/callback churn.

  const STORE_ID = "interact_store";
  const GRAPH_ID = "chart";
  const THROTTLE_MS = 80;

  function nowMs() {
    return (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
  }

  function findGraphDiv() {
    // Dash renders dcc.Graph as a container with id=GRAPH_ID and a child .js-plotly-plot.
    const host = document.getElementById(GRAPH_ID);
    if (!host) return null;
    return host.querySelector(".js-plotly-plot");
  }

  function setInteractHoverPrice(px) {
    try {
      if (!window.dash_clientside || typeof window.dash_clientside.set_props !== "function") {
        return;
      }
      window.dash_clientside.set_props(STORE_ID, { data: { hover_price: px } });
    } catch (e) {
      // ignore
    }
  }

  function clearInteractHoverPrice() {
    setInteractHoverPrice(null);
  }

  let lastT = 0;
  let lastV = null;

  function attach() {
    const gd = findGraphDiv();
    if (!gd) return;
    if (gd.__paHoverAttached) return;
    gd.__paHoverAttached = true;

    gd.addEventListener("mousemove", function (ev) {
      const t = nowMs();
      if (t - lastT < THROTTLE_MS) return;
      lastT = t;

      try {
        const full = gd._fullLayout;
        const ya = full && full.yaxis;
        if (!ya) return;
        // Relative to plot area (robust to subplot key not being "xy")
        const plots = full && full._plots;
        const plotKey = plots && (plots.xy ? "xy" : Object.keys(plots)[0]);
        const plotObj = plotKey ? plots[plotKey] : null;
        const yaxisObj = plotObj && plotObj.yaxis;
        const plotTop = yaxisObj && yaxisObj._offset;
        const plotH = yaxisObj && yaxisObj._length;
        if (typeof plotTop !== "number" || typeof plotH !== "number") return;

        const ypx = ev.clientY - gd.getBoundingClientRect().top;
        const yInPlot = ypx - plotTop;
        if (yInPlot < 0 || yInPlot > plotH) {
          // outside plot area
          if (lastV !== null) {
            lastV = null;
            clearInteractHoverPrice();
          }
          return;
        }

        // Plotly axis has p2l (pixel->linear) using pixels from top of plot.
        const val = ya.p2l(yInPlot);
        if (typeof val !== "number" || !isFinite(val)) return;

        // Snap to 0.01 for display stability.
        const snapped = Math.round(val * 100) / 100;
        if (lastV === null || Math.abs(snapped - lastV) >= 0.01) {
          lastV = snapped;
          setInteractHoverPrice(snapped);
        }
      } catch (e) {
        // ignore
      }
    });

    gd.addEventListener("mouseleave", function () {
      lastV = null;
      clearInteractHoverPrice();
    });
  }

  // Re-attach on load and periodically (Dash rerenders graph div).
  function boot() {
    attach();
    setInterval(attach, 1000);
  }

  if (document.readyState === "complete" || document.readyState === "interactive") {
    boot();
  } else {
    document.addEventListener("DOMContentLoaded", boot);
  }
})();

