import type {Place} from "./corridor.js";

const escapeHtml = (value : string) => value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
}[character]!));

export const routePage = (places : Array<Place>, map : unknown) => {
    // Safe to inline: JSON with "<" escaped cannot close the script tag.
    const mapJson = JSON.stringify(map).replace(/</g, "\\u003c");
    const options = places.map((place) => `<option value="${escapeHtml(place.id)}">${escapeHtml(place.name)}</option>`).join("");
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PedalAtlas</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,560;9..144,680&family=Outfit:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root { --paper: #f4efe4; --ink: #1c1914; --spruce: #1b4332; --spruce-deep: #10281e; --copper: #b85c38; --line: #ddcfc0; --card: #fbf7f0; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; color: var(--ink); background: var(--paper); font-family: Outfit, sans-serif; display: grid; grid-template-rows: auto 1fr auto; }
    header { display: flex; justify-content: space-between; align-items: end; gap: 1rem; padding: 0.85rem 1.25rem; background: var(--spruce-deep); color: #f6f1e6; }
    .wordmark { margin: 0; font-family: Fraunces, serif; font-size: 1.7rem; }
    .tagline, .meta { margin: 0; color: #6a5f54; font-size: 0.85rem; }
    header .tagline { color: #e7d7c4; }
    main { display: grid; grid-template-columns: 280px 1fr; gap: 1.25rem; padding: 1.25rem; }
    form, aside, .stage { background: var(--card); border: 1px solid var(--line); padding: 0.9rem 1rem; }
    label { display: grid; gap: 0.25rem; margin-bottom: 0.7rem; font-size: 0.85rem; }
    select, button { font: inherit; }
    select { padding: 0.45rem 0.5rem; border: 1px solid var(--line); background: white; }
    button { border: 0; background: var(--spruce); color: #f6f1e6; padding: 0.5rem 0.7rem; cursor: pointer; }
    button:disabled { opacity: 0.6; cursor: wait; }
    h2 { font-family: Fraunces, serif; margin: 0 0 0.4rem; }
    .stage { border-top: 1px solid var(--line); padding: 0.7rem 0; background: transparent; border-left: 0; border-right: 0; }
    .stage strong { color: var(--spruce); }
    #related li { list-style: none; border-bottom: 1px solid var(--line); padding: 0.45rem 0; }
    #related ul { margin: 0; padding: 0; }
    #related span { display: block; color: var(--copper); font-size: 0.78rem; }
    #status { min-height: 1.2rem; }
    footer { padding: 0.8rem 1.25rem 1.1rem; }
    footer a { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.75rem; opacity: 0.7; text-decoration: none; color: inherit; }
    .brief { background: var(--card); border: 1px solid var(--line); border-left: 4px solid var(--spruce); padding: 0.8rem 1rem; margin: 0.8rem 0; }
    .brief.flagged { border-left-color: var(--copper); }
    .brief p { margin: 0.3rem 0 0; line-height: 1.45; }
    .review-actions { display: flex; gap: 0.5rem; margin-top: 0.7rem; }
    .review-actions .withhold { background: var(--copper); }
    #trace { margin-top: 1rem; overflow-x: auto; }
    #trace table { border-collapse: collapse; width: 100%; font-size: 0.8rem; }
    #trace th, #trace td { text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--line); vertical-align: top; }
    #trace th { font-weight: 600; color: #6a5f54; }
    #trace code { font-size: 0.78rem; }
    #map { height: 380px; border: 1px solid var(--line); margin-bottom: 0.8rem; background: #e8e2d6; }
    .legend { display: flex; flex-wrap: wrap; gap: 0.3rem 0.9rem; font-size: 0.75rem; color: #6a5f54; margin: -0.4rem 0 0.8rem; }
    .legend i { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 0.3rem; }
    .sample { margin: 0; padding: 0.45rem 1.25rem; background: #efe4d3; color: #6a4a2e; font-size: 0.8rem; }
    @media (max-width: 800px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <div>
      <p class="wordmark">PedalAtlas</p>
      <p class="tagline">Explore further. Ride informed.</p>
    </div>
  </header>
  <p class="sample">Sample data: every rider note in this demo is simulated. The real group chats stay private.</p>
  <main>
    <form id="route-plan">
      <h2>Plan a route</h2>
      <p class="meta">A request becomes a route job. Stages and regional chat are attached as it moves.</p>
      <label>From <select id="start" name="startId">${options}</select></label>
      <label>To <select id="end" name="endId">${options}</select></label>
      <label>Brief language <select id="language" name="language">
        <option>English</option><option>Español</option><option>Deutsch</option><option>Français</option><option>Português</option>
      </select></label>
      <button type="submit">Show stages</button>
      <p id="status" class="meta" role="status"></p>
    </form>
    <section>
      <div id="map" role="region" aria-label="Map of the corridor, the planned route and sample rider notes"></div>
      <div class="legend" id="legend"></div>
      <div id="brief"></div>
      <div id="result"></div>
      <aside id="related" hidden></aside>
      <section id="trace" hidden></section>
    </section>
  </main>
  <footer>
    <a href="https://anbaric.ai">
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect width="12" height="12" rx="2" fill="#1c1914"/><path d="M3 9 L6 3 L9 9" fill="none" stroke="#f4efe4" stroke-width="1.2"/></svg>
      Built with Anbaric
    </a>
  </footer>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const start = document.querySelector("#start");
    const end = document.querySelector("#end");
    const button = document.querySelector("#route-plan button");
    const status = document.querySelector("#status");
    const result = document.querySelector("#result");
    const related = document.querySelector("#related");
    const language = document.querySelector("#language");
    const briefBox = document.querySelector("#brief");
    const traceBox = document.querySelector("#trace");
    if ([...start.options].some((option) => option.value === "fairbanks")) start.value = "fairbanks";
    if ([...end.options].some((option) => option.value === "whitehorse")) end.value = "whitehorse";

    const escapeText = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));

    const MAP = ${mapJson};
    const NEED_COLORS = {road: "#b85c38", stay: "#1b4332", water: "#2b6cb0", resupply: "#8a6d1d", border: "#7b2d8b", safety: "#c0392b", season: "#5b6b73"};
    const atlasMap = L.map("map", {scrollWheelZoom: false}).setView([60.5, -135], 4);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 12, attribution: "&copy; OpenStreetMap contributors"}).addTo(atlasMap);
    MAP.segments.forEach((segment) => L.polyline([segment.from, segment.to], {color: "#7d8f86", weight: 2, opacity: 0.6}).bindTooltip(segment.highway).addTo(atlasMap));
    const placeAt = new Map(MAP.places.map((place) => [place.name, [place.lat, place.lon]]));
    const notesLayer = L.layerGroup().addTo(atlasMap);
    const routeLayer = L.layerGroup().addTo(atlasMap);
    const offsets = new Map();
    MAP.notes.forEach((note) => {
      const at = placeAt.get(note.placeLabel);
      if (!at) return;
      const count = offsets.get(note.placeLabel) || 0;
      offsets.set(note.placeLabel, count + 1);
      const spot = [at[0] + count * 0.12, at[1] + count * 0.2];
      L.circleMarker(spot, {radius: 6, color: "#fff", weight: 1.5, fillColor: NEED_COLORS[note.need] || "#444", fillOpacity: 0.95})
        .bindPopup("<strong>" + escapeText(note.label) + "</strong> · " + escapeText(note.placeLabel) + " · " + escapeText(note.when) + "<br>" + escapeText(note.text) + "<br><em>Simulated rider account</em>")
        .addTo(notesLayer);
    });
    document.querySelector("#legend").innerHTML = Object.entries(NEED_COLORS).map(([need, color]) => "<span><i style='background:" + color + "'></i>" + need + "</span>").join("")
      + "<span>" + MAP.notes.length + " sample notes</span>";
    const drawRoute = (stages) => {
      routeLayer.clearLayers();
      const lines = (stages || []).filter((stage) => stage.from && stage.to).map((stage) => [stage.from, stage.to]);
      if (!lines.length) return;
      lines.forEach((line) => L.polyline(line, {color: "#1b4332", weight: 5}).addTo(routeLayer));
      atlasMap.fitBounds(L.latLngBounds(lines.flat()), {padding: [30, 30]});
    };

    const settled = (job) => {
      const state = String(job.status || "").toLowerCase();
      return ["ready", "unroutable", "withheld", "review"].includes(job.state) || state === "failed" || state === "stalled";
    };

    const renderTrace = (props) => {
      const steps = props.trace || [];
      if (!steps.length) { traceBox.hidden = true; return; }
      const total = steps.reduce((sum, step) => sum + (step.costUsd || 0), 0);
      traceBox.hidden = false;
      traceBox.innerHTML = "<h2>Who did what</h2><p class='meta'>Each step is an Anbaric actor, recorded in the job's audit trail. Model cost for this route: $" + total.toFixed(5) + "</p>"
        + "<table><thead><tr><th>Step</th><th>Actor</th><th>Model</th><th>Time</th><th>Tokens in/out</th><th>Cost</th><th>Why this model</th></tr></thead><tbody>"
        + steps.map((step) => "<tr><td>" + escapeText(step.step) + "</td><td><code>" + escapeText(step.actor) + "</code></td><td><code>" + escapeText(step.model) + "</code></td><td>"
          + escapeText(step.ms) + " ms</td><td>" + escapeText(step.inputTokens) + " / " + escapeText(step.outputTokens) + "</td><td>$" + Number(step.costUsd || 0).toFixed(5) + "</td><td>" + escapeText(step.note) + "</td></tr>").join("")
        + "</tbody></table>";
    };

    const decide = async (jobId, approved, useRevision) => {
      briefBox.querySelectorAll("button").forEach((b) => b.disabled = true);
      const response = await fetch("routes/" + encodeURIComponent(jobId) + "/decision", {
        method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({approved, useRevision: Boolean(useRevision)}),
      });
      if (!response.ok) { status.textContent = (await response.json()).error || "That decision was not saved."; return; }
      await follow(jobId, ["ready", "withheld"]);
    };

    const renderBrief = (job) => {
      const props = job.properties || {};
      if (!props.brief) {
        briefBox.innerHTML = ["assembled", "briefed", "flagged"].includes(job.state) ? "<p class='meta'>Claude is writing the brief…</p>" : "";
        return;
      }
      const flagged = typeof props.riskScore === "number" && !["assembled", "briefed"].includes(job.state) && props.riskScore >= 0.5;
      const risk = typeof props.riskScore === "number" ? " · Jev " + escapeText(props.riskReason) + " risk " + Number(props.riskScore).toFixed(2) : "";
      let head = "Rider brief" + risk;
      let body = "<p>" + escapeText(props.brief) + "</p>";
      if (job.state === "review") {
        head = "Held for a moderator" + risk;
        if (props.reviewNote) body += "<p class='meta'><strong>Claude Opus advises " + escapeText(props.reviewRecommendation) + ":</strong> " + escapeText(props.reviewNote) + "</p>";
        if (props.reviewRevision) body += "<p><strong>Claude Opus's edit:</strong> " + escapeText(props.reviewRevision) + "</p>";
        body += "<div class='review-actions'>"
          + (props.reviewRevision ? "<button type='button' data-approve='true' data-revision='true'>Publish Opus's edit</button>" : "")
          + "<button type='button' data-approve='true'>" + (props.reviewRevision ? "Publish original" : "Approve for riders") + "</button>"
          + "<button type='button' class='withhold' data-approve='false'>Withhold</button></div>";
      } else if (job.state === "withheld") {
        head = "Withheld by a moderator" + risk;
        body = "<p>A moderator kept this brief back. The stages below are still shown.</p>";
      } else if (job.state === "ready" && props.reviewRecommendation === "approve" && props.approved === undefined) {
        head = "Rider brief · approved by Claude Opus review" + risk;
        if (props.reviewNote) body += "<p class='meta'>" + escapeText(props.reviewNote) + "</p>";
      } else if (job.state === "ready" && props.approved === true) {
        head = "Rider brief · approved by " + escapeText(props.reviewedBy) + risk;
      }
      briefBox.innerHTML = "<div class='brief" + (flagged ? " flagged" : "") + "'><strong>" + head + "</strong>" + body + "</div>";
      briefBox.querySelectorAll("[data-approve]").forEach((button) =>
        button.addEventListener("click", () => decide(job.id, button.dataset.approve === "true", button.dataset.revision === "true")));
    };

    const render = (job) => {
      const props = job.properties || {};
      renderBrief(job);
      renderTrace(props);
      if (String(job.status).toLowerCase() === "failed") {
        status.textContent = "The route stopped. The job failed before the stages were saved.";
        return;
      }
      if (job.state === "requested") {
        status.textContent = "Assembling the schematic route…";
        return;
      }
      if (job.state === "unroutable") {
        status.textContent = "No schematic highway joins those places.";
        result.innerHTML = "<h2>" + escapeText(props.fromName) + " to " + escapeText(props.toName) + "</h2><p>The published reference set has no connected line to draw.</p>";
        related.hidden = true;
        return;
      }
      drawRoute(props.stages);
      status.textContent = {assembled: "Claude Haiku is writing the brief…", briefed: "Jev is scoring the risk…", flagged: "Jev flagged it. Claude Opus is reviewing…",
        review: "Jev flagged this brief. A moderator decides before riders see it.", withheld: "Brief withheld."}[job.state] || "Route ready.";
      const stages = (props.stages || []).map((stage) =>
        '<div class="stage"><strong>' + escapeText(stage.title) + '</strong><p class="meta">' + escapeText(stage.highway) + " · about " + escapeText(stage.distanceKm) + " km</p></div>"
      ).join("");
      const lede = props.outcome === "same"
        ? "That is the same place."
        : "About " + escapeText(props.distanceKm) + " km as straight lines between towns. Not a checked cycling itinerary.";
      result.innerHTML = "<h2>" + escapeText(props.fromName) + " to " + escapeText(props.toName) + "</h2><p>" + lede + "</p>" + stages;
      const notes = props.relatedNotes || [];
      if (!notes.length) {
        related.hidden = true;
        related.innerHTML = "";
        return;
      }
      related.hidden = false;
      related.innerHTML = "<p class='meta'>" + escapeText(props.relatedTitle) + " chat</p><ul>" + notes.map((note) => {
        const where = [note.placeLabel, note.when].filter(Boolean).join(" · ");
        return "<li><strong>" + escapeText(note.label) + "</strong><span>" + escapeText(where) + "</span>" + escapeText(note.text) + "</li>";
      }).join("") + "</ul>";
    };

    const follow = (jobId, stopAt) => new Promise((resolve) => {
      let polls = 0;
      const tick = async () => {
        const response = await fetch("routes/" + encodeURIComponent(jobId));
        const job = await response.json();
        render(job);
        if (stopAt ? stopAt.includes(job.state) : settled(job)) return resolve();
        if (polls++ >= 30) {
          status.textContent = "Still assembling. Check the job again in a moment.";
          return resolve();
        }
        setTimeout(tick, 1000);
      };
      tick();
    });

    document.querySelector("#route-plan").addEventListener("submit", async (event) => {
      event.preventDefault();
      button.disabled = true;
      status.textContent = "Route requested — assembling the stages…";
      result.innerHTML = "";
      briefBox.innerHTML = "";
      traceBox.hidden = true;
      related.hidden = true;
      try {
        const response = await fetch("routes", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({startId: start.value, endId: end.value, language: language.value}),
        });
        const job = await response.json();
        if (!response.ok) {
          status.textContent = job.error || "That route could not be requested.";
          return;
        }
        await follow(job.id);
      } finally {
        button.disabled = false;
      }
    });
    const reviewId = new URLSearchParams(location.search).get("review");
    if (reviewId) follow(reviewId);
  </script>
</body>
</html>`;
};
