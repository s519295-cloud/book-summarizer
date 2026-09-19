const state = {
  links: [],
  selectedUrl: null,
  title: "",
  author: "",
  depth: "short",
  summary: "",
  plan: "",
  essay: ""
};

const $ = (id) => document.getElementById(id);

function setBox(id, type, text) {
  const el = $(id);
  el.className = "state-box " + type;
  el.textContent = text;
  el.classList.remove("hidden");
}
function hideBox(id) { $(id).classList.add("hidden"); }

function hostLabel(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return url; }
}

function renderSources() {
  const grid = $("sourcesGrid");
  grid.replaceChildren();
  state.links.forEach((url, index) => {
    const card = document.createElement("div");
    card.className = "source-card" + (state.selectedUrl === url ? " selected" : "");

    const icon = document.createElement("div");
    icon.className = "source-icon";
    icon.textContent = index === 0 ? "▤" : index === 1 ? "✦" : "▥";

    const body = document.createElement("div");
    const name = document.createElement("div");
    name.className = "source-name";
    name.textContent = hostLabel(url);
    const status = document.createElement("div");
    status.className = "source-status";
    const dot = document.createElement("span");
    dot.className = "status-dot";
    status.append(dot, document.createTextNode(index === 0 ? "Полный текст найден" : "Текст доступен"));
    body.append(name, status);

    const btn = document.createElement("button");
    btn.className = "source-btn";
    btn.type = "button";
    btn.textContent = state.selectedUrl === url ? "Источник выбран" : "Выбрать источник";
    btn.addEventListener("click", () => {
      state.selectedUrl = url;
      renderSources();
      $("depthSection").classList.remove("hidden");
      $("generateBtn").disabled = false;
      $("depthSection").scrollIntoView({behavior:"smooth", block:"center"});
    });

    card.append(icon, body, btn);
    if (state.selectedUrl === url) {
      const badge = document.createElement("div");
      badge.className = "check-badge";
      badge.textContent = "✓";
      card.append(badge);
    }
    grid.append(card);
  });
}

function setDepth(depth) {
  state.depth = depth;
  document.querySelectorAll(".depth-card").forEach(btn => {
    btn.classList.toggle("selected", btn.dataset.depth === depth);
  });
}
document.querySelectorAll(".depth-card").forEach(btn => {
  btn.addEventListener("click", () => setDepth(btn.dataset.depth));
});

$("searchBtn").addEventListener("click", async () => {
  const title = $("bookTitle").value.trim();
  const author = $("bookAuthor").value.trim();
  if (!title) {
    setBox("searchState", "error", "Введите название произведения.");
    return;
  }
  state.title = title;
  state.author = author;
  state.selectedUrl = null;
  state.summary = "";
  state.plan = "";
  state.essay = "";
  $("searchBtn").disabled = true;
  setBox("searchState", "loading", "Ищем источники с текстом произведения…");

  try {
    const response = await fetch("/search", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({title, author})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Не удалось выполнить поиск.");
    state.links = data.links || [];
    if (!state.links.length) throw new Error("Подходящие источники не найдены.");
    renderSources();
    $("sourcesSection").classList.remove("hidden");
    $("depthSection").classList.add("hidden");
    $("workspaceSection").classList.add("hidden");
    $("essaySection").classList.add("hidden");
    setBox("searchState", "success", "Найдено источников: " + state.links.length);
    $("sourcesSection").scrollIntoView({behavior:"smooth", block:"start"});
  } catch (err) {
    setBox("searchState", "error", err.message);
  } finally {
    $("searchBtn").disabled = false;
  }
});

$("generateBtn").addEventListener("click", async () => {
  if (!state.selectedUrl) return;
  $("generateBtn").disabled = true;
  setBox("summaryState", "loading", "Скачиваем текст и создаём пересказ…");
  $("workspaceSection").classList.remove("hidden");
  $("summaryText").textContent = "";
  try {
    const response = await fetch("/summarize", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({url:state.selectedUrl, title:state.title, depth:state.depth})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Не удалось создать пересказ.");
    state.summary = data.summary || "";
    $("bookResultTitle").textContent = state.title;
    $("bookResultMeta").textContent = [state.author, depthLabel(state.depth), readingTime(state.depth)].filter(Boolean).join(" · ");
    $("summaryText").textContent = state.summary;
    hideBox("summaryState");
    $("essaySection").classList.remove("hidden");
    $("essayTopic").value = state.title ? 'Тема произведения «' + state.title + '»' : "";
    activateTab("summary");
    $("workspaceSection").scrollIntoView({behavior:"smooth", block:"start"});
  } catch (err) {
    setBox("summaryState", "error", err.message);
  } finally {
    $("generateBtn").disabled = false;
  }
});

function depthLabel(depth) {
  return {
    very_short:"Очень краткий пересказ",
    short:"Краткий пересказ",
    medium:"Средний пересказ",
    detailed:"Подробный пересказ",
    deep:"Глубокий пересказ"
  }[depth] || "Пересказ";
}
function readingTime(depth) {
  return {
    very_short:"~1–2 минуты",
    short:"~2–3 минуты",
    medium:"~3–4 минуты",
    detailed:"~4–5 минут",
    deep:"~6–7 минут"
  }[depth] || "";
}

function activateTab(tab) {
  document.querySelectorAll(".tab").forEach(el => el.classList.toggle("active", el.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach(el => el.classList.add("hidden"));
  $("panel-" + tab).classList.remove("hidden");
}
document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => activateTab(tab.dataset.tab)));

$("copyBtn").addEventListener("click", async () => {
  if (!state.summary) return;
  await navigator.clipboard.writeText(state.summary);
  const old = $("copyBtn").textContent;
  $("copyBtn").textContent = "Скопировано";
  setTimeout(() => $("copyBtn").textContent = old, 1200);
});
$("shorterBtn").addEventListener("click", () => {
  const order = ["very_short","short","medium","detailed","deep"];
  const i = order.indexOf(state.depth);
  if (i > 0) {
    setDepth(order[i - 1]);
    $("depthSection").scrollIntoView({behavior:"smooth", block:"center"});
  }
});
$("longerBtn").addEventListener("click", () => {
  const order = ["very_short","short","medium","detailed","deep"];
  const i = order.indexOf(state.depth);
  if (i >= 0 && i < order.length - 1) {
    setDepth(order[i + 1]);
    $("depthSection").scrollIntoView({behavior:"smooth", block:"center"});
  }
});

$("planBtn").addEventListener("click", async () => {
  const topic = $("essayTopic").value.trim();
  if (!topic) {
    setBox("essayState", "error", "Введите тему сочинения.");
    return;
  }
  if (!state.summary) {
    setBox("essayState", "error", "Сначала создайте пересказ.");
    return;
  }
  $("planBtn").disabled = true;
  setBox("essayState", "loading", "Формируем план сочинения…");
  try {
    const response = await fetch("/plan", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({title:state.title, topic, summary:state.summary})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Не удалось создать план.");
    state.plan = data.plan || "";
    $("planContent").textContent = state.plan;
    $("planContent").classList.remove("hidden");
    $("writeEssayBtn").disabled = false;
    $("panel-plan").replaceChildren();
    const planText = document.createElement("div");
    planText.className = "plan-content";
    planText.textContent = state.plan;
    $("panel-plan").append(planText);
    activateTab("plan");
    hideBox("essayState");
  } catch (err) {
    setBox("essayState", "error", err.message);
  } finally {
    $("planBtn").disabled = false;
  }
});

$("writeEssayBtn").addEventListener("click", async () => {
  const topic = $("essayTopic").value.trim();
  if (!state.plan) {
    setBox("essayState", "error", "Сначала составьте план.");
    return;
  }
  $("writeEssayBtn").disabled = true;
  setBox("essayState", "loading", "Пишем сочинение по плану…");
  try {
    const response = await fetch("/write_essay", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({title:state.title, topic, plan:state.plan, summary:state.summary})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Не удалось написать сочинение.");
    state.essay = data.essay || "";
    $("panel-essay").replaceChildren();
    const essayText = document.createElement("div");
    essayText.className = "essay-content";
    essayText.textContent = state.essay;
    $("panel-essay").append(essayText);
    activateTab("essay");
    hideBox("essayState");
  } catch (err) {
    setBox("essayState", "error", err.message);
  } finally {
    $("writeEssayBtn").disabled = false;
  }
});

document.querySelectorAll(".nav-item").forEach(item => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    item.classList.add("active");
    const target = item.dataset.target;
    if (target === "book") {
      window.scrollTo({top:0, behavior:"smooth"});
      return;
    }
    if (!state.summary) {
      $("searchSection").scrollIntoView({behavior:"smooth", block:"start"});
      return;
    }
    if (target === "summary") {
      activateTab("summary");
      $("workspaceSection").scrollIntoView({behavior:"smooth", block:"start"});
    } else if (target === "plan") {
      activateTab("plan");
      $("workspaceSection").scrollIntoView({behavior:"smooth", block:"start"});
    } else if (target === "essay") {
      activateTab("essay");
      $("workspaceSection").scrollIntoView({behavior:"smooth", block:"start"});
    } else {
      activateTab(target);
      $("workspaceSection").scrollIntoView({behavior:"smooth", block:"start"});
    }
  });
});

$("bookTitle").addEventListener("keydown", e => { if (e.key === "Enter") $("searchBtn").click(); });
$("bookAuthor").addEventListener("keydown", e => { if (e.key === "Enter") $("searchBtn").click(); });
