// gamevid UI — plain JS, no build step. The server's project.json is the only state;
// every edit is sent to the API and the page re-renders from the response.

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtT = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(2).padStart(5, "0")}`;
const KINDS = ["hook", "body", "payoff", "cta"];

let view = null;       // {project, timeline, timeline_error, stage_status}
let pid = null;
let mark = { in: null, out: null };
let pollTimer = null;

async function api(path, opts = {}) {
  const res = await fetch(path, opts.body instanceof FormData ? opts : {
    ...opts, headers: { "Content-Type": "application/json" },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    toast(msg);
    throw new Error(msg);
  }
  return data;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), 6000);
}

const fileUrl = (rel) => `/api/projects/${pid}/file/${rel}`;

// ------------------------------------------------------------------ routing

async function route() {
  clearInterval(pollTimer);
  const m = location.hash.match(/^#\/p\/([a-z0-9-]+)/);
  $("#home").hidden = !!m;
  $("#project").hidden = !m;
  if (m) {
    pid = m[1];
    view = await api(`/api/projects/${pid}`);
    $("#crumb").textContent = view.project.title;
    renderProject();
    pollJobs();
    pollTimer = setInterval(pollJobs, 1500);
  } else {
    pid = null; $("#crumb").textContent = "";
    const list = await api("/api/projects");
    $("#project-list").innerHTML = list.map((p) =>
      `<li><a href="#/p/${p.id}">${esc(p.title)}</a> <span class="hint">${esc(p.created_at)}</span></li>`
    ).join("") || "<li class='hint'>No projects yet.</li>";
  }
}

$("#new-project").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const v = await api("/api/projects", { method: "POST", body: {
    title: f.get("title"), topic: f.get("topic"),
    bullets: f.get("bullets").split("\n").map((s) => s.trim()).filter(Boolean),
  }});
  location.hash = `#/p/${v.project.id}`;
};

// ------------------------------------------------------------------ project page

function renderProject() {
  const p = view.project;
  $("#stage-bar").innerHTML = Object.entries(view.stage_status)
    .map(([k, v]) => `<span class="pill ${v}">${k}: ${v}</span>`).join("");
  renderSections(p);
  renderNarration(p);
  renderCaptions(p);
  renderFootage(p);
  renderTimeline();
  renderSettings(p);
  renderRenders(p);
}

let sectionsDirty = false;  // don't clobber unsaved edits when the page refreshes
function renderSections(p) {
  if (sectionsDirty) return;
  const rows = p.sections.length ? p.sections : [{ id: null, kind: "hook", text: "" }];
  $("#section-editor").innerHTML = rows.map((s, i) => sectionRow(s, i)).join("");
}

function sectionRow(s, i) {
  return `<div class="sec-row" data-id="${s.id ?? ""}">
    <span class="mono">${i + 1}</span>
    <select>${KINDS.map((k) => `<option ${k === s.kind ? "selected" : ""}>${k}</option>`).join("")}</select>
    <textarea>${esc(s.text)}</textarea>
    <button class="secondary del" title="Remove">×</button></div>`;
}

$("#add-section").onclick = () => {
  sectionsDirty = true;
  const n = $("#section-editor").children.length;
  $("#section-editor").insertAdjacentHTML("beforeend", sectionRow({ kind: "body", text: "" }, n));
};
$("#section-editor").oninput = () => (sectionsDirty = true);
$("#section-editor").onclick = (e) => { if (e.target.classList.contains("del")) { e.target.parentElement.remove(); sectionsDirty = true; } };
$("#save-sections").onclick = async () => {
  const body = [...document.querySelectorAll(".sec-row")].map((r) => ({
    id: r.dataset.id || null, kind: r.querySelector("select").value, text: r.querySelector("textarea").value,
  })).filter((s) => s.text.trim());
  view = await api(`/api/projects/${pid}/sections`, { method: "PUT", body });
  sectionsDirty = false;
  renderProject(); toast("Sections saved");
};

function renderNarration(p) {
  const n = p.narration;
  $("#narration-player").hidden = !n;
  if (n && !$("#narration-player").src.includes(n.sha)) $("#narration-player").src = fileUrl(n.file) + `?v=${n.sha}`;
  $("#narration-info").textContent = n ? `${n.duration.toFixed(2)} s` : "No narration yet — render uses estimated timings.";
}

async function upload(path, file) {
  const fd = new FormData(); fd.append("file", file);
  toast(`Uploading ${file.name}…`);
  return api(path, { method: "POST", body: fd });
}

$("#upload-narration").onclick = async () => {
  const f = $("#narration-file").files[0];
  if (!f) return toast("Choose a file first");
  view = await upload(`/api/projects/${pid}/narration`, f);
  renderProject(); toast("Narration uploaded. Run captions to split it into sections.");
};

function renderCaptions(p) {
  const st = p.stages.captions?.output;
  if (!st) { $("#captions-report").innerHTML = ""; return; }
  $("#captions-report").innerHTML = `
    <p>Script match: <b>${Math.round(st.match_ratio * 100)}%</b>
    ${st.warning ? `<span class="warn">${esc(st.warning)}</span>` : ""}</p>
    ${st.skipped.length ? `<p class="hint">Not heard in recording: ${esc(st.skipped.join(" "))}</p>` : ""}
    ${st.extra.length ? `<p class="hint">Said but not in script (kept in captions): ${esc(st.extra.join(" "))}</p>` : ""}`;
}

$("#run-captions").onclick = () => startJob("captions");
$("#run-assemble").onclick = async () => { await saveSettings(false); startJob("assemble"); };

async function startJob(kind) {
  await api(`/api/projects/${pid}/jobs/${kind}`, { method: "POST" });
  pollJobs();
}

// ------------------------------------------------------------------ footage & clip marking

function renderFootage(p) {
  const names = Object.keys(p.footage);
  $("#footage-list").innerHTML = names.map((n) => {
    const f = p.footage[n];
    return `<li><span class="mono">${esc(n)}</span>
      <span class="hint">${f.width}×${f.height} · ${f.fps} fps · ${fmtT(f.duration)}</span>
      <button class="secondary" data-del="${esc(n)}">Delete</button></li>`;
  }).join("") || "<li class='hint'>No footage yet.</li>";
  $("#marker").hidden = !names.length || !p.sections.length;

  const cur = $("#scrub-source").value;
  $("#scrub-source").innerHTML = names.map((n) => `<option ${n === cur ? "selected" : ""}>${esc(n)}</option>`).join("");
  if ($("#scrub-source").value && !$("#scrub").dataset.src) loadScrub();
  const curSec = $("#mark-section").value;
  $("#mark-section").innerHTML = p.sections.map((s, i) =>
    `<option value="${s.id}" ${s.id === curSec ? "selected" : ""}>${i + 1} · ${s.kind} — ${esc(s.text.slice(0, 40))}</option>`).join("");
}

$("#footage-list").onclick = async (e) => {
  const n = e.target.dataset.del;
  if (n && confirm(`Delete ${n}?`)) { view = await api(`/api/projects/${pid}/footage/${encodeURIComponent(n)}`, { method: "DELETE" }); renderProject(); }
};

$("#upload-footage").onclick = async () => {
  for (const f of $("#footage-file").files) view = await upload(`/api/projects/${pid}/footage`, f);
  renderProject(); toast("Uploaded. Making preview copies in the background…");
};

function loadScrub() {
  const n = $("#scrub-source").value;
  if (!n) return;
  const v = $("#scrub");
  v.dataset.src = n;
  v.src = fileUrl(`proxies/${n}.mp4`);
  v.onerror = () => toast("Preview copy not ready yet — check Jobs, then reselect the file.");
  mark = { in: null, out: null }; showMark();
}
$("#scrub-source").onchange = loadScrub;

function showMark() {
  $("#mark-range").textContent = `IN ${mark.in == null ? "—" : fmtT(mark.in)}  OUT ${mark.out == null ? "—" : fmtT(mark.out)}`
    + (mark.in != null && mark.out != null ? `  (${(mark.out - mark.in).toFixed(2)} s)` : "");
}
$("#mark-in").onclick = () => { mark.in = $("#scrub").currentTime; showMark(); };
$("#mark-out").onclick = () => { mark.out = $("#scrub").currentTime; showMark(); };
document.addEventListener("keydown", (e) => {
  if ($("#marker").hidden || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
  if (e.key === "i") $("#mark-in").click();
  if (e.key === "o") $("#mark-out").click();
});

$("#add-clip").onclick = async () => {
  if (mark.in == null || mark.out == null || mark.out <= mark.in) return toast("Set IN then OUT (OUT after IN).");
  const sec = view.project.sections.find((s) => s.id === $("#mark-section").value);
  const clips = [...sec.clips, { source: $("#scrub-source").value, t_in: +mark.in.toFixed(3), t_out: +mark.out.toFixed(3), crop_x: 0.5 }];
  await saveClips(sec.id, clips);
  mark = { in: null, out: null }; showMark();
};

async function saveClips(sid, clips) {
  view = await api(`/api/projects/${pid}/sections/${sid}/clips`, { method: "PUT", body: clips });
  renderProject();
}

function renderTimeline() {
  const tl = view.timeline;
  if (!tl) { $("#timeline-view").innerHTML = `<p class="error">${esc(view.timeline_error || "")}</p>`; return; }
  $("#timeline-view").innerHTML = `<p class="hint">Total ${tl.duration.toFixed(2)} s${tl.estimated ? " (estimated — no narration timing yet)" : ""}</p>` +
    tl.sections.map((s, i) => {
      const sec = view.project.sections[i];
      const ratio = s.marked_seconds / s.duration;
      const color = ratio >= 1 ? "var(--ok)" : ratio > 0 ? "var(--warn)" : "var(--bad)";
      return `<div class="tl-sec" data-sid="${sec.id}">
        <div class="tl-head"><b>${i + 1} · ${sec.kind}</b>
          <span class="mono">${fmtT(s.start)} → ${fmtT(s.end)} · need ${s.duration.toFixed(2)} s · marked ${s.marked_seconds.toFixed(2)} s</span></div>
        <div class="bar"><span style="width:${Math.min(100, ratio * 100)}%;background:${color}"></span></div>
        ${s.warnings.map((w) => `<div class="warn">${esc(w)}</div>`).join("")}
        ${sec.clips.map((c, k) => `<div class="clip" data-k="${k}">
          <span class="mono">${esc(c.source)} ${fmtT(c.t_in)}–${fmtT(c.t_out)}</span>
          <label class="inline" title="Horizontal position for 9:16 crop">crop <input type="range" min="0" max="1" step="0.05" value="${c.crop_x}" data-act="crop"></label>
          <button class="secondary" data-act="up" title="Move up">↑</button>
          <button class="secondary" data-act="rm" title="Remove">×</button></div>`).join("")}
        ${view.project.narration && i > 0 ? `<div class="clip hint">starts at
          <input type="number" step="0.05" value="${sec.audio?.start ?? s.start}" data-act="start" style="width:6em"> s
          ${sec.audio?.source === "manual" ? "(manual)" : ""}</div>` : ""}
      </div>`;
    }).join("");
}

$("#timeline-view").addEventListener("change", async (e) => {
  const box = e.target.closest(".tl-sec"); if (!box) return;
  const sid = box.dataset.sid, sec = view.project.sections.find((s) => s.id === sid);
  if (e.target.dataset.act === "crop") {
    const k = +e.target.closest(".clip").dataset.k;
    const clips = sec.clips.map((c, j) => (j === k ? { ...c, crop_x: +e.target.value } : c));
    await saveClips(sid, clips);
  }
  if (e.target.dataset.act === "start") {
    view = await api(`/api/projects/${pid}/sections/${sid}/start`, { method: "PUT", body: { start: +e.target.value } });
    renderProject();
  }
});
$("#timeline-view").addEventListener("click", async (e) => {
  const act = e.target.dataset.act; if (act !== "rm" && act !== "up") return;
  const sid = e.target.closest(".tl-sec").dataset.sid, k = +e.target.closest(".clip").dataset.k;
  const clips = [...view.project.sections.find((s) => s.id === sid).clips];
  if (act === "rm") clips.splice(k, 1);
  if (act === "up" && k > 0) [clips[k - 1], clips[k]] = [clips[k], clips[k - 1]];
  await saveClips(sid, clips);
});

// ------------------------------------------------------------------ settings & renders

const CAPTION_FIELDS = [
  ["enabled", "checkbox"], ["font", "text"], ["color", "color"], ["highlight", "color"],
  ["uppercase", "checkbox"], ["size_vertical", "number"], ["size_horizontal", "number"],
  ["max_words_vertical", "number"], ["max_words_horizontal", "number"], ["outline", "number"],
];

let musicLoaded = false;
async function renderSettings(p) {
  document.querySelectorAll("input[name=fmt]").forEach((c) => (c.checked = p.formats.includes(c.value)));
  $("#vertical-fill").value = p.styles.vertical_fill;
  $("#music-db").value = p.music.volume_db;
  $("#music-duck").checked = p.music.duck;
  if (!musicLoaded) {
    musicLoaded = true;
    const tracks = await api("/api/music");
    $("#music-file").insertAdjacentHTML("beforeend", tracks.map((t) => `<option>${esc(t)}</option>`).join(""));
  }
  $("#music-file").value = p.music.file || "";
  const cs = p.styles.captions;
  $("#caption-style").innerHTML = CAPTION_FIELDS.map(([k, type]) =>
    `<label class="inline">${k.replace(/_/g, " ")} <input data-k="${k}" type="${type}"
      ${type === "checkbox" ? (cs[k] ? "checked" : "") : `value="${esc(cs[k])}"`} ${type === "number" ? 'style="width:5em"' : ""}></label>`).join("");
}

async function saveSettings(notify = true) {
  const p = view.project;
  const captions = { ...p.styles.captions };
  document.querySelectorAll("#caption-style input").forEach((i) => {
    captions[i.dataset.k] = i.type === "checkbox" ? i.checked : i.type === "number" ? +i.value : i.value;
  });
  view = await api(`/api/projects/${pid}/settings`, { method: "PUT", body: {
    formats: [...document.querySelectorAll("input[name=fmt]:checked")].map((c) => c.value),
    styles: { ...p.styles, vertical_fill: $("#vertical-fill").value, captions },
    music: { file: $("#music-file").value || null, volume_db: +$("#music-db").value, duck: $("#music-duck").checked },
  }});
  renderProject();
  if (notify) toast("Settings saved");
}
$("#save-settings").onclick = () => saveSettings();

function renderRenders(p) {
  const out = p.stages.assemble?.output;
  if (!out) { $("#renders").innerHTML = ""; return; }
  const stale = view.stage_status.assemble === "stale";
  $("#renders").innerHTML = `
    ${stale ? `<p class="warn">Project changed since this render — render again to see the changes.</p>` : ""}
    ${out.estimated_timing ? `<p class="warn">Rendered with estimated timings (no narration).</p>` : ""}
    ${out.warnings.map((w) => `<div class="warn">${esc(w)}</div>`).join("")}
    <div class="renders">${Object.entries(out.files).map(([fmt, f]) =>
      `<figure><video class="${fmt}" controls src="${fileUrl(f)}"></video>
       <figcaption><a href="${fileUrl(f)}" download>${fmt}.mp4</a></figcaption></figure>`).join("")}</div>`;
}

// ------------------------------------------------------------------ jobs

let lastDone = new Set();
async function pollJobs() {
  if (!pid) return;
  const list = await fetch(`/api/jobs?project=${pid}`).then((r) => r.json());
  $("#job-list").innerHTML = list.slice(0, 8).map((j) => `<li>
    <b>${j.kind}</b> ${j.args?.filename ? esc(j.args.filename) : ""}
    ${j.status === "running" ? `<progress value="${j.progress}"></progress>` : `<span class="pill ${j.status === "done" ? "done" : j.status === "failed" ? "stale" : "pending"}">${j.status}</span>`}
    <span class="hint ${j.status === "failed" ? "error" : ""}">${esc(j.message)}</span></li>`).join("") || "<li class='hint'>No jobs yet.</li>";
  $("#run-captions").disabled = $("#run-assemble").disabled =
    list.some((j) => (j.kind === "captions" || j.kind === "assemble") && (j.status === "running" || j.status === "queued"));

  // When a job finishes, refresh the project so new outputs appear.
  const done = new Set(list.filter((j) => j.status !== "running" && j.status !== "queued").map((j) => j.id));
  const fresh = [...done].some((id) => !lastDone.has(id));
  if (fresh) {
    view = await api(`/api/projects/${pid}`);
    renderProject();
    if ($("#scrub").dataset.src && $("#scrub").error) loadScrub();
  }
  lastDone = done;
}

window.addEventListener("hashchange", route);
route();
