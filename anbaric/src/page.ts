import type {Place} from "./corridor.js";

const escapeHtml = (value : string) => value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
}[character]!));

export const routePage = (places : Array<Place>) => {
    const options = places.map((place) => `<option value="${escapeHtml(place.id)}">${escapeHtml(place.name)}</option>`).join("");
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PedalAtlas</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
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
  <main>
    <form id="route-plan">
      <h2>Plan a route</h2>
      <p class="meta">A request becomes a route job. Stages and regional chat are attached as it moves.</p>
      <label>From <select id="start" name="startId">${options}</select></label>
      <label>To <select id="end" name="endId">${options}</select></label>
      <button type="submit">Show stages</button>
      <p id="status" class="meta" role="status"></p>
    </form>
    <section>
      <div id="result"></div>
      <aside id="related" hidden></aside>
    </section>
  </main>
  <footer>
    <a href="https://anbaric.ai">
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect width="12" height="12" rx="2" fill="#1c1914"/><path d="M3 9 L6 3 L9 9" fill="none" stroke="#f4efe4" stroke-width="1.2"/></svg>
      Built with Anbaric
    </a>
  </footer>
  <script>
    const start = document.querySelector("#start");
    const end = document.querySelector("#end");
    const button = document.querySelector("#route-plan button");
    const status = document.querySelector("#status");
    const result = document.querySelector("#result");
    const related = document.querySelector("#related");
    if ([...start.options].some((option) => option.value === "fairbanks")) start.value = "fairbanks";
    if ([...end.options].some((option) => option.value === "whitehorse")) end.value = "whitehorse";

    const escapeText = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));

    const settled = (job) => {
      const state = String(job.status || "").toLowerCase();
      return job.state === "ready" || job.state === "unroutable" || state === "failed" || state === "stalled";
    };

    const render = (job) => {
      const props = job.properties || {};
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
      status.textContent = "Route ready.";
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

    const follow = (jobId) => new Promise((resolve) => {
      let polls = 0;
      const tick = async () => {
        const response = await fetch("routes/" + encodeURIComponent(jobId));
        const job = await response.json();
        render(job);
        if (settled(job)) return resolve();
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
      related.hidden = true;
      try {
        const response = await fetch("routes", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({startId: start.value, endId: end.value}),
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
  </script>
</body>
</html>`;
};
