const form = document.getElementById("ask-form");
const qInput = document.getElementById("q");
const askBtn = document.getElementById("ask-btn");
const resultEl = document.getElementById("result");

function escapeHtml(s){
  return String(s).replace(/[&<>"]/g,
    c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
}

// Plain text: escape, preserve line breaks (CSS white-space:pre-wrap), and turn
// [n] markers into links that jump to source n. Markdown/LaTeX is deferred.
function renderAnswer(text){
  return escapeHtml(text).replace(/\[(\d+)\]/g,
    '<a class="cite" href="#src-$1">[$1]</a>');
}

function render(data){
  let html = '<div class="answer">' + renderAnswer(data.answer || "") + "</div>";

  if(data.figures && data.figures.length){
    html += '<div class="section-h">Figures</div>';
    data.figures.forEach(f => {
      const cap = f.caption ? escapeHtml(f.caption) : `${escapeHtml(f.book)}, p.${f.page}`;
      html += `<figure><img src="${escapeHtml(f.url)}" alt="${cap}" loading="lazy">`
        + `<figcaption>Source [${f.source_n}] — ${escapeHtml(f.book)}, p.${f.page}`
        + (f.caption ? " — " + escapeHtml(f.caption) : "")
        + `</figcaption></figure>`;
    });
  }

  if(data.citations && data.citations.length){
    html += '<div class="section-h">Sources</div>';
    data.citations.forEach(c => {
      html += `<div class="src" id="src-${c.n}">[${c.n}] ${escapeHtml(c.book)}`
        + (c.chapter ? ", " + escapeHtml(c.chapter) : "")
        + `, p.${c.page}</div>`;
    });
  }
  resultEl.innerHTML = html;
}

async function ask(question){
  askBtn.disabled = true;
  askBtn.textContent = "Searching…";
  resultEl.innerHTML = '<div class="status">Searching textbooks…</div>';
  try {
    const r = await fetch("/ask", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question}),
    });
    if(!r.ok) throw new Error("HTTP " + r.status);
    render(await r.json());
  } catch(e){
    resultEl.innerHTML = '<div class="status error">Couldn\'t reach the textbook server — '
      + 'is it running? (' + escapeHtml(e.message) + ')</div>';
  } finally {
    askBtn.disabled = false;
    askBtn.textContent = "Ask";
  }
}

form.onsubmit = (e) => {
  e.preventDefault();
  const q = qInput.value.trim();
  if(q) ask(q);
};
