const HISTORY_KEY = "neuro-rag-history";
const form = document.getElementById("ask-form");
const qInput = document.getElementById("q");
const askBtn = document.getElementById("ask-btn");
const resultEl = document.getElementById("result");
const historyEl = document.getElementById("history");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");

function escapeHtml(s){
  return s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
}

// Minimal markdown: bold, headings, and bullet lines. Then citation chips.
function renderAnswer(text){
  const lines = escapeHtml(text).split("\n");
  let html = "", inList = false;
  for(const line of lines){
    const b = line.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    if(/^\s*[-*]\s+/.test(line)){
      if(!inList){ html += "<ul>"; inList = true; }
      html += "<li>" + b.replace(/^\s*[-*]\s+/, "") + "</li>";
    } else {
      if(inList){ html += "</ul>"; inList = false; }
      if(/^#{1,3}\s/.test(line)) html += "<h3>" + b.replace(/^#{1,3}\s/, "") + "</h3>";
      else if(line.trim() === "") html += "";
      else html += "<p>" + b + "</p>";
    }
  }
  if(inList) html += "</ul>";
  // [n] citation chips that scroll to the source row
  return html.replace(/\[(\d+)\]/g,
    '<span class="cite" onclick="scrollToSource($1)">[$1]</span>');
}

window.scrollToSource = function(n){
  const el = document.getElementById("src-" + n);
  if(el) el.scrollIntoView({behavior:"smooth", block:"center"});
};

function plainTextForCopy(question, data){
  let out = "Q: " + question + "\n\n" + data.answer + "\n\nSources:\n";
  data.citations.forEach(c => {
    out += `[${c.n}] ${c.book}${c.chapter ? ", " + c.chapter : ""}, p.${c.page}\n`;
  });
  return out;
}

function render(question, data){
  let html = '<div class="answer">' + renderAnswer(data.answer) + "</div>";
  html += '<div class="toolbar"><button id="copy-btn">Copy</button>';
  if(navigator.share) html += '<button id="share-btn">Share</button>';
  html += "</div>";
  if(data.figures && data.figures.length){
    html += '<div class="section-h">Figures</div>';
    data.figures.forEach(f => {
      html += `<figure class="fig"><img src="${escapeHtml(f.url)}" alt="${escapeHtml(f.caption)}" `
        + `data-fig-url="${escapeHtml(f.url)}"><figcaption>[${f.source_n}] `
        + `${escapeHtml(f.book)}, p.${f.page} — ${escapeHtml(f.caption)}</figcaption></figure>`;
    });
  }
  if(data.citations && data.citations.length){
    html += '<div class="section-h">Sources</div>';
    data.citations.forEach(c => {
      html += `<div class="src" id="src-${c.n}">[${c.n}] ${escapeHtml(c.book)}`
        + `${c.chapter ? ", " + escapeHtml(c.chapter) : ""}, p.${c.page}</div>`;
    });
  }
  resultEl.innerHTML = html;
  resultEl.querySelectorAll(".fig img").forEach(img => {
    img.onclick = () => openFig(img.dataset.figUrl);
  });
  const copyBtn = document.getElementById("copy-btn");
  copyBtn.onclick = () => navigator.clipboard.writeText(plainTextForCopy(question, data))
    .then(() => { copyBtn.textContent = "Copied"; })
    .catch(() => { copyBtn.textContent = "Copy failed"; });
  const shareBtn = document.getElementById("share-btn");
  if(shareBtn) shareBtn.onclick = () =>
    navigator.share({title:"Neuro RAG", text:plainTextForCopy(question, data)}).catch(() => {});
}

window.openFig = function(url){
  lightboxImg.src = url; lightbox.classList.remove("hidden");
};
lightbox.onclick = () => lightbox.classList.add("hidden");
document.addEventListener("keydown", e => { if(e.key === "Escape") lightbox.classList.add("hidden"); });

function loadHistory(){ try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; }
  catch { return []; } }
function saveHistory(list){ localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, 20))); }
function pushHistory(question){
  const list = loadHistory().filter(q => q !== question);
  list.unshift(question); saveHistory(list); renderHistory();
}
function renderHistory(){
  const list = loadHistory();
  historyEl.innerHTML = list.map(q =>
    `<button>${escapeHtml(q)}</button>`).join("");
  [...historyEl.querySelectorAll("button")].forEach((b, i) => {
    b.onclick = () => { qInput.value = list[i]; historyEl.classList.add("hidden"); ask(list[i]); };
  });
}
document.getElementById("history-toggle").onclick = () => {
  renderHistory(); historyEl.classList.toggle("hidden");
};

async function ask(question){
  askBtn.disabled = true;
  resultEl.innerHTML = '<div class="status"><span class="spinner"></span>Searching textbooks…</div>';
  try {
    const r = await fetch("/ask", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({question})});
    if(r.status === 401){ window.location.href = "/login"; return; }
    if(!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    render(question, data);
    pushHistory(question);
  } catch(e){
    resultEl.innerHTML = '<div class="status error">Can\'t reach the textbook server — '
      + 'is the server running? '
      + '<button id="retry-btn">Retry</button></div>';
    document.getElementById("retry-btn").onclick = () => ask(question);
  } finally {
    askBtn.disabled = false;
  }
}
window.ask = ask;

form.onsubmit = (e) => {
  e.preventDefault();
  const q = qInput.value.trim();
  if(q) ask(q);
};

if("serviceWorker" in navigator)
  navigator.serviceWorker.register("/sw.js").catch(() => {});
