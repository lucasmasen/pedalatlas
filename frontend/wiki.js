function escapeWiki(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[character]));
}

const CATEGORY_LABELS = {
  trending: "Trending",
  stage: "Stages",
  unplaced: "Unplaced",
  elsewhere: "Outside this route",
  overview: "Route",
  town: "Towns",
  highway: "Highways",
  junction: "Junctions",
  border: "Borders",
  region: "Regions",
  park: "Parks",
  settlement: "Settlements",
  place: "Places",
};

const wiki = { articles: [], category: "all", query: "" };

function showView(name) {
  document.querySelector("#view-map").hidden = name !== "map";
  document.querySelector("#view-wiki").hidden = name !== "wiki";
  document.querySelector("#show-map").setAttribute("aria-current", name === "map" ? "true" : "false");
  document.querySelector("#show-wiki").setAttribute("aria-current", name === "wiki" ? "true" : "false");
  if (name === "map" && window.atlasMap) window.atlasMap.invalidateSize();
}

function filteredArticles() {
  const query = wiki.query.trim().toLowerCase();
  return wiki.articles.filter((article) => {
    const categoryOk = wiki.category === "all" || article.category === wiki.category;
    const text = `${article.title} ${article.summary}`.toLowerCase();
    return categoryOk && (!query || text.includes(query));
  });
}

function renderList() {
  const list = document.querySelector("#wiki-list");
  const rows = filteredArticles();
  list.innerHTML = rows.map((article) => `
    <li>
      <button type="button" data-id="${escapeWiki(article.id)}" ${wiki.current === article.id ? 'aria-current="true"' : ""}>
        <strong>${escapeWiki(article.title)}</strong>
        <span>${escapeWiki(article.category === "trending" ? `${article.heat} notes` : (article.highway || CATEGORY_LABELS[article.category] || article.category))}</span>
      </button>
    </li>
  `).join("") || "<li class='meta'>No published page matches.</li>";
  list.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => openWiki(button.dataset.id));
  });
}

function renderRelated(chat) {
  const box = document.querySelector("#related-notes");
  if (!chat || !chat.notes || !chat.notes.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  box.hidden = false;
  const notes = chat.notes.map((note) => {
    const where = [note.place_label, note.when].filter(Boolean).join(" · ");
    return `
      <li>
        <button type="button" data-id="${escapeWiki(chat.id)}">
          <strong>${escapeWiki(note.label)}</strong>
          <span>${escapeWiki(where)}</span>
          <em>${escapeWiki(note.text)}</em>
        </button>
      </li>
    `;
  }).join("");
  box.innerHTML = `<p class="meta">${escapeWiki(chat.title)} chat</p><ul>${notes}</ul>`;
  box.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => openWiki(button.dataset.id));
  });
}

function noteBits(line) {
  return [line.place_label, line.when, line.text].filter(Boolean).join(" · ");
}

function renderArticle(article) {
  wiki.current = article.id;
  renderList();
  renderRelated(article.related_chat);
  const facts = article.key_facts.map((fact) => `
    <div><dt>${escapeWiki(fact.label)}</dt><dd>${escapeWiki(fact.value)}</dd></div>
  `).join("");
  const sections = article.sections.map((section) => {
    const paragraphs = (section.paragraphs || []).map((paragraph) => `<p>${escapeWiki(paragraph)}</p>`).join("");
    const items = (section.items || []).map((item) => `<li>${escapeWiki(item)}</li>`).join("");
    return `
      <details ${section.open ? "open" : ""}>
        <summary>${escapeWiki(section.title)}</summary>
        ${paragraphs}
        ${items ? `<ul>${items}</ul>` : ""}
      </details>
    `;
  }).join("");
  const links = (article.links || []).map((link) => `
    <button type="button" data-id="${escapeWiki(link.id)}">${escapeWiki(link.title)}</button>
  `).join("");
  const page = document.querySelector("#wiki-page");
  page.innerHTML = `
    <div class="wiki-layout">
      <div>
        <p class="eyebrow">${article.group === "trending" ? "Trending route" : article.group === "stage" ? "Stage" : article.group === "overview" ? "Route" : "Place"}</p>
        <h2>${escapeWiki(article.title)}</h2>
        <p class="lede">${escapeWiki(article.summary)}</p>
        ${sections}
        ${links ? `<p class="wiki-links">${links}</p>` : ""}
        <p class="meta">Source: ${escapeWiki(article.source)}</p>
      </div>
      <aside class="infobox">
        <h3>Key facts</h3>
        <dl>${facts}</dl>
      </aside>
    </div>
  `;
  page.querySelectorAll(".wiki-links button").forEach((button) => {
    button.addEventListener("click", () => openWiki(button.dataset.id));
  });
}

async function openWiki(articleId) {
  showView("wiki");
  const page = document.querySelector("#wiki-page");
  page.innerHTML = "<p>Loading page…</p>";
  const response = await fetch(`/api/wiki/${encodeURIComponent(articleId)}`);
  if (!response.ok) {
    page.innerHTML = "<p>That page is not published.</p>";
    renderRelated(null);
    return;
  }
  renderArticle(await response.json());
}

function addGuideMessage(role, html) {
  const log = document.querySelector("#guide-log");
  const item = document.createElement("div");
  item.className = `guide-${role}`;
  item.innerHTML = html;
  log.appendChild(item);
  log.scrollTop = log.scrollHeight;
  return item;
}

async function askGuide(message) {
  addGuideMessage("user", `<p>${escapeWiki(message)}</p>`);
  const response = await fetch("/api/guide", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    addGuideMessage("agent", "<p>The guide could not answer that.</p>");
    return;
  }
  const result = await response.json();
  const citations = (result.citations || []).map((citation) => `
    <button type="button" data-id="${escapeWiki(citation.id)}">${escapeWiki(citation.title)}</button>
  `).join("");
  let route = "";
  if (result.route && result.route.legs) {
    route = `<ol>${result.route.legs.map((leg) => `
      <li>${escapeWiki(leg.highway)}: ${escapeWiki(leg.from_name)} to ${escapeWiki(leg.to_name)}
      <span class="meta"> · about ${escapeWiki(leg.distance_km_approximate)} km</span></li>
    `).join("")}</ol>`;
  }
  const item = addGuideMessage("agent", `<p>${escapeWiki(result.answer)}</p>${route}${citations ? `<p class="wiki-links">${citations}</p>` : ""}`);
  item.querySelectorAll(".wiki-links button").forEach((button) => {
    button.addEventListener("click", () => openWiki(button.dataset.id));
  });
}

async function bootWiki() {
  const response = await fetch("/api/wiki");
  const payload = await response.json();
  wiki.articles = payload.articles;
  const preferred = ["overview", "trending", "stage", "unplaced", "elsewhere", "town", "highway", "junction", "border", "region", "park", "settlement", "place"];
  const categories = [...new Set(wiki.articles.map((article) => article.category))];
  categories.sort((left, right) => {
    const leftRank = preferred.indexOf(left);
    const rightRank = preferred.indexOf(right);
    return (leftRank < 0 ? 99 : leftRank) - (rightRank < 0 ? 99 : rightRank);
  });
  const select = document.querySelector("#wiki-category");
  categories.forEach((category) => {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = CATEGORY_LABELS[category] || category;
    select.appendChild(option);
  });
  const trending = wiki.articles.filter((article) => article.category === "trending");
  const trendingList = document.querySelector("#trending-list");
  trendingList.innerHTML = trending.map((article) => `
    <li><button type="button" data-id="${escapeWiki(article.id)}"><strong>${escapeWiki(article.title)}</strong><span>${escapeWiki(article.heat)} notes</span></button></li>
  `).join("") || "<li class='meta'>No stretch has a chat note yet.</li>";
  trendingList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => openWiki(button.dataset.id));
  });
  renderList();
  document.querySelector("#wiki-query").addEventListener("input", (event) => {
    wiki.query = event.target.value;
    renderList();
  });
  select.addEventListener("change", (event) => {
    wiki.category = event.target.value;
    renderList();
  });
  document.querySelector("#show-map").addEventListener("click", () => showView("map"));
  document.querySelector("#show-wiki").addEventListener("click", () => {
    showView("wiki");
    if (!wiki.current) openWiki("corridor");
  });
  document.querySelector("#show-guide").addEventListener("click", () => {
    document.querySelector("#guide").hidden = false;
  });
  document.querySelector("#close-guide").addEventListener("click", () => {
    document.querySelector("#guide").hidden = true;
  });
  document.querySelector("#guide-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.querySelector("#guide-input");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    askGuide(message);
  });
  const places = wiki.articles
    .filter((article) => article.group === "place" && article.category !== "highway" && article.category !== "region")
    .sort((left, right) => left.title.localeCompare(right.title));
  for (const select of [document.querySelector("#route-start"), document.querySelector("#route-end")]) {
    select.innerHTML = places.map((place) => `<option value="${escapeWiki(place.id)}">${escapeWiki(place.title)}</option>`).join("");
  }
  const start = document.querySelector("#route-start");
  const end = document.querySelector("#route-end");
  if ([...start.options].some((option) => option.value === "fairbanks")) start.value = "fairbanks";
  if ([...end.options].some((option) => option.value === "whitehorse")) end.value = "whitehorse";
  document.querySelector("#route-plan").addEventListener("submit", async (event) => {
    event.preventDefault();
    showView("wiki");
    const response = await fetch(`/api/route?start=${encodeURIComponent(start.value)}&end=${encodeURIComponent(end.value)}`);
    const page = document.querySelector("#wiki-page");
    if (!response.ok) {
      page.innerHTML = "<p>No schematic path joins those places.</p>";
      renderRelated(null);
      return;
    }
    renderRoute(await response.json());
  });
  window.openWiki = openWiki;
}

function renderRoute(bundle) {
  wiki.current = "";
  renderList();
  renderRelated(bundle.related_chat);
  const highway = (bundle.highway_notes || []).map((card) => `
    <section class="stage-card">
      <p><strong>Whole ${escapeWiki(card.highway)}</strong> · ${escapeWiki(card.label)} · as of ${escapeWiki(card.as_of)}</p>
      <p class="meta">Shown once for this highway.</p>
      <ul>${(card.current || []).map((line) => `<li>${escapeWiki(noteBits(line))}</li>`).join("")}</ul>
    </section>
  `).join("");
  const stages = (bundle.stages || []).map((stage) => {
    const needs = (stage.needs || []).map((need) => {
      const tip = need.current[0];
      const where = tip.place_label ? `${escapeWiki(tip.place_label)} · ` : "";
      return `
      <li><strong>${escapeWiki(need.label)}</strong> · as of ${escapeWiki(need.as_of)} · ${where}${escapeWiki(tip.text)}</li>
    `;
    }).join("");
    return `
      <section class="stage-card">
        <button type="button" data-id="${escapeWiki(stage.id)}">${escapeWiki(stage.title)}</button>
        <p class="meta">${escapeWiki(stage.highway)} · about ${escapeWiki(stage.distance_km_approximate)} km</p>
        ${needs ? `<ul>${needs}</ul>` : "<p>No chat note names this stretch.</p>"}
      </section>
    `;
  }).join("");
  const page = document.querySelector("#wiki-page");
  page.innerHTML = `
    <p class="eyebrow">Route</p>
    <h2>${escapeWiki(bundle.from_name)} to ${escapeWiki(bundle.to_name)}</h2>
    <p class="lede">About ${escapeWiki(bundle.distance_km_approximate)} km as straight lines between towns. Stages are in ride order.</p>
    ${highway}
    ${stages}
  `;
  page.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => openWiki(button.dataset.id));
  });
}

bootWiki();
