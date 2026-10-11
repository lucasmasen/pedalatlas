const styles = {
  spine: { color: "#1b4332", weight: 4 },
  alternative: { color: "#b85c38", weight: 3, dashArray: "7 6" },
  spur: { color: "#245566", weight: 2, dashArray: "2 6" },
};

const state = {
  map: null,
  lines: {},
  markers: null,
  locations: [],
  segments: [],
  selected: null,
  showNearby: false,
};

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[character]));
}

function visibleLocations() {
  return state.locations.filter((place) => state.showNearby || place.scope === "corridor");
}

function renderAnchors() {
  const list = document.querySelector("#anchor-list");
  list.innerHTML = state.locations.filter((place) => place.featured).map((place) => `
    <li>
      <button type="button" data-id="${escapeHtml(place.id)}" ${state.selected === place.id ? 'aria-current="true"' : ""}>
        ${escapeHtml(place.name)}
      </button>
    </li>
  `).join("");
  list.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => selectPlace(button.dataset.id));
  });
}

function drawMap() {
  Object.values(state.lines).forEach((layer) => layer.clearLayers());
  state.markers.clearLayers();
  const visible = new Set(visibleLocations().map((place) => place.id));
  state.segments.forEach((segment) => {
    if (!visible.has(segment.from_id) || !visible.has(segment.to_id)) return;
    const role = state.lines[segment.role] ? segment.role : "alternative";
    L.polyline([segment.from, segment.to], styles[role])
      .bindTooltip(segment.highway)
      .addTo(state.lines[role]);
  });
  visibleLocations().forEach((place) => {
    const marker = L.circleMarker([place.lat, place.lon], {
      radius: place.featured ? 8 : 5,
      color: place.id === state.selected ? "#b85c38" : "#1b4332",
      fillColor: place.featured ? "#fbf7f0" : "#7ea2ad",
      fillOpacity: 1,
      weight: 2,
    });
    marker.bindTooltip(place.name);
    marker.on("click", () => selectPlace(place.id));
    marker.addTo(state.markers);
  });
}

async function selectPlace(locationId) {
  state.selected = locationId;
  renderAnchors();
  drawMap();
  const sheet = document.querySelector("#sheet");
  sheet.innerHTML = "<p>Loading place…</p>";
  const response = await fetch(`/api/locations/${encodeURIComponent(locationId)}`);
  if (!response.ok) {
    sheet.innerHTML = "<p>That place is not on this atlas.</p>";
    return;
  }
  const place = await response.json();
  const point = state.locations.find((item) => item.id === locationId);
  if (point) state.map.setView([point.lat, point.lon], Math.max(state.map.getZoom(), 6));
  const segments = (place.roads && place.roads.segments) || [];
  const segmentHtml = segments.map((segment) => {
    const other = segment.from_id === place.id ? segment.to_name : segment.from_name;
    return `<li>${escapeHtml(segment.highway)} toward ${escapeHtml(other)}
      <span class="meta"> · about ${escapeHtml(segment.distance_km_approximate)} km, surface not verified</span></li>`;
  }).join("");
  const drafts = place.community.private_drafts;
  const draftText = drafts === 0
    ? "No unpublished community drafts are tied to this place."
    : `${drafts} unpublished community draft${drafts === 1 ? "" : "s"} mention this place. The wording is not shown.`;
  sheet.innerHTML = `
    <p class="eyebrow">${escapeHtml(place.region)}</p>
    <h2>${escapeHtml(place.name)}</h2>
    <p>${escapeHtml(place.summary)}</p>
    <p class="meta">${place.lat.toFixed(3)}, ${place.lon.toFixed(3)} · centroid for orientation</p>
    <div class="callout">
      <strong>Roads</strong>
      <p>${escapeHtml(place.roads.summary)}</p>
      <ul class="segments">${segmentHtml}</ul>
    </div>
    <div class="season">
      <strong>Seasonal background</strong>
      <p>${escapeHtml(place.season.summary)}</p>
      <p class="meta">Background only, not a forecast. The published wiki page repeats this limit.</p>
    </div>
    <p><button type="button" id="open-wiki-place">Open wiki page</button></p>
    <p class="private">${escapeHtml(draftText)} Published community claims: ${place.community.published}.</p>
  `;
  sheet.querySelector("#open-wiki-place").addEventListener("click", () => window.openWiki?.(locationId));
}

async function boot() {
  const response = await fetch("/api/map");
  const documentData = await response.json();
  state.locations = documentData.locations;
  state.segments = documentData.segments;
  state.map = L.map("map");
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 14,
  }).addTo(state.map);
  ["spine", "alternative", "spur"].forEach((role) => {
    state.lines[role] = L.layerGroup().addTo(state.map);
  });
  state.markers = L.layerGroup().addTo(state.map);
  const points = visibleLocations().map((place) => [place.lat, place.lon]);
  state.map.fitBounds(points, { padding: [28, 28] });
  renderAnchors();
  drawMap();
  document.querySelector("#show-nearby").addEventListener("change", (event) => {
    state.showNearby = event.target.checked;
    drawMap();
  });
  window.atlasMap = state.map;
}

boot();
