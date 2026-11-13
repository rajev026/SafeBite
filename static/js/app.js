/* SafeBite front end: talks to the Flask JSON API, renders results, runs the camera. */
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const STATUS = {
  green:  { label: "Safe to eat",  chip: "bg-go text-white",   border: "border-go",   dot: "bg-go" },
  yellow: { label: "Ask the chef", chip: "bg-wait text-ink",   border: "border-wait", dot: "bg-wait" },
  red:    { label: "Do not eat",   chip: "bg-stop text-white", border: "border-stop", dot: "bg-stop" },
};
const getStatus = s => STATUS[s] || { label: "Notice", chip: "bg-ink/80 text-white", border: "border-ink/40", dot: "bg-ink/60" };

/* ------------------------------------------------------------ rendering */
const words = ws => (ws || []).map(w => `<span${w.low ? ' class="low" title="Low OCR confidence"' : ""}>${esc(w.t ?? w.text ?? "")}</span>`).join(" ");
const chip  = s => {
  const st = getStatus(s);
  return `<span class="inline-flex rounded-full px-3 py-1 text-sm font-semibold ${st.chip}">${st.label}</span>`;
};

function verdictHtml(v) {
  if (!v) return "";
  const reasons = (v.reasons || []).map(r => `<li>${esc(r)}</li>`).join("");
  const flags = (v.disease_flags || []).map(f =>
    `<li class="${f.level === "red" ? "text-stop" : "text-amber-700"} font-medium">${esc(f.msg)}</li>`).join("");
  const detected = v.detected || [];
  const badges = detected.map(a =>
    `<span class="bg-red-50 text-red-700 border border-red-200 px-2 py-0.5 rounded text-xs mt-1 inline-block mr-1 font-medium">${esc(a)}</span>`).join("");
  return `<ul class="mt-2 space-y-1 text-sm">${reasons}${flags}</ul>${badges ? `<div class="mt-2">${badges}</div>` : ""}`;
}

function renderProduct(r) {
  const v = r.verdict || {};
  const st = getStatus(v.status);
  const nut = (r.nutrition && r.nutrition.length) ? `
    <table class="mt-4 text-sm w-full max-w-md"><caption class="text-left font-semibold pb-1">Nutrition per 100 g (Open Food Facts)</caption>
    ${r.nutrition.map(n => `<tr class="border-t border-ink/10"><td class="py-1">${esc(n.label)}</td><td class="text-right">${esc(n.value)} ${esc(n.unit)}</td></tr>`).join("")}</table>` : "";
  return `<div class="reveal bg-white rounded-xl p-6 shadow-sm border-l-8 ${st.border}">
    <div class="flex flex-wrap gap-5">
      ${r.image ? `<img src="${esc(r.image)}" alt="" class="w-24 h-24 object-contain rounded">` : ""}
      <div class="flex-1 min-w-[16rem]">
        <h2 class="font-display text-2xl font-bold">${esc(r.name)}</h2>
        <p class="text-sm text-ink/70">${esc(r.brand || "")} ${esc(r.quantity || "")} &middot; barcode ${esc(r.code || "")}</p>
        <div class="mt-3">${chip(v.status)}</div>${verdictHtml(v)}
      </div>
      <div class="text-sm">${r.nutriscore ? `<p>Nutri-Score <strong class="uppercase">${esc(r.nutriscore)}</strong></p>` : ""}
        ${r.nova ? `<p>NOVA group <strong>${esc(r.nova)}</strong></p>` : ""}</div>
    </div>
    ${r.ingredients ? `<p class="mt-4 text-sm"><strong>Ingredients:</strong> ${esc(r.ingredients)}</p>` : ""}${nut}
  </div>`;
}

function renderText(r) {
  const v = r.verdict || {};
  const st = getStatus(v.status);
  return `<div class="reveal bg-white rounded-xl p-6 shadow-sm border-l-8 ${st.border}">
    <div class="flex items-center justify-between">
      <span class="text-xs font-semibold uppercase tracking-wider text-ink/60">${esc(r.via || "Text detection")}</span>
      ${r.confidence ? `<span class="text-xs text-ink/60 font-medium">OCR Confidence: ${r.confidence}%</span>` : ""}
    </div>
    <div class="mt-3 bg-mist/70 border border-ink/10 rounded-lg p-3 text-sm font-mono whitespace-pre-wrap max-h-60 overflow-y-auto leading-relaxed">${esc(r.text)}</div>
    <div class="mt-4">${chip(v.status)}</div>
    ${verdictHtml(v)}
  </div>`;
}

function dishHtml(it) {
  const v = it.verdict || {};
  const st = getStatus(v.status);
  const descRaw = (it.desc || []).map(d => (d || []).map(w => w.t ?? w.text ?? "").join(" ")).join(" ");
  const allText = ((it.name_text || "") + " " + descRaw).toLowerCase();
  const descHtml = (it.desc || []).length
    ? `<p class="text-sm text-ink/80 mt-1">${it.desc.map(d => words(d)).join("<br>")}</p>`
    : "";
  return `<article class="dish bg-white rounded-lg p-4 shadow-sm border-l-8 ${st.border}"
      data-status="${v.status || 'yellow'}" data-text="${esc(allText)}">
    <div class="flex justify-between items-start gap-3">
      <h4 class="font-semibold text-base">${words(it.name)}</h4>
      ${it.price ? `<span class="font-semibold whitespace-nowrap text-sm bg-mist px-2 py-0.5 rounded">${esc(it.price)}</span>` : ""}
    </div>
    ${descHtml}
    <div class="mt-2 flex flex-wrap items-center gap-2">${chip(v.status || "yellow")}
      <button type="button" data-dish="${esc(it.name_text || '')}" class="nutri text-xs underline text-ink/70 hover:text-ink">Nutrition</button>
    </div>
    ${verdictHtml(v)}
    <div class="nutri-out mt-2 text-xs"></div>
  </article>`;
}

function renderMenu(r) {
  const cols = (r.columns || []).length;
  const grid = cols === 2 ? "md:grid-cols-2" : cols >= 3 ? "md:grid-cols-3" : "";
  const counts = r.counts || { red: 0, yellow: 0, green: 0 };
  const total = counts.red + counts.yellow + counts.green;
  const filters = ["all", "red", "yellow", "green"].map(f => {
    const n = f === "all" ? total : counts[f];
    const label = f === "all" ? "All" : getStatus(f).label;
    return `<button data-filter="${f}" class="filter rounded-full border border-ink/25 px-3 py-1 text-sm transition hover:border-ink font-medium">${label} (${n})</button>`;
  }).join("");
  const body = (r.columns || []).map(col => `<div class="space-y-3">${col.map(it => {
    if (it.type === "section") {
      const secV = it.verdict ? `<span class="ml-2">${chip(it.verdict.status)}</span>` : "";
      return `<h3 class="font-display text-xl font-bold pt-3 border-b border-ink/10 pb-1 flex items-center">${words(it.words)}${secV}</h3>`;
    }
    return dishHtml(it);
  }).join("")}</div>`).join("");

  const rawSection = r.raw_text ? `
    <details class="no-print mt-6 text-xs text-ink/70">
      <summary class="cursor-pointer underline font-medium">View full text detected from image</summary>
      <div class="mt-2 bg-mist/60 border border-ink/10 rounded p-3 font-mono whitespace-pre-wrap max-h-52 overflow-y-auto">${esc(r.raw_text)}</div>
    </details>` : "";

  return `<div class="reveal">
    <div class="flex flex-wrap items-center gap-3 mb-3">
      <h2 class="font-display text-2xl font-bold">Menu results</h2>
      <span class="text-xs text-ink/60">Text confidence ${r.confidence || 0}%. Underlined words were hard to read.</span>
      <button onclick="window.print()" class="no-print ml-auto text-sm underline hover:text-ink">Print or save as PDF</button>
    </div>
    ${r.qr_url ? `<p class="mb-3 text-sm rounded bg-white px-4 py-2 border border-ink/10">A QR code linking to <a class="underline font-medium text-go" href="${esc(r.qr_url)}" target="_blank" rel="noopener noreferrer">${esc(r.qr_url)}</a> was also found.</p>` : ""}
    ${total === 0 ? `<p class="rounded bg-amber-100 text-amber-900 px-4 py-3">No readable dishes found. Retake the photo flat, in good light, filling the frame.</p>` : `
    <div class="no-print flex flex-wrap items-center gap-2 mb-4">${filters}
      <input id="dish-search" type="search" placeholder="Search dishes" class="ml-auto rounded border border-ink/20 px-3 py-1.5 text-sm"></div>`}
    <div class="grid gap-x-8 gap-y-3 ${grid}">${body}</div>
    <p id="no-match" class="hidden mt-4 text-sm font-medium text-ink/70">No dishes match this filter.</p>
    ${rawSection}
  </div>`;
}

function applyFilter() {
  const active = $(".filter[data-filter].bg-ink")?.dataset.filter || "all";
  const q = ($("#dish-search")?.value || "").toLowerCase().trim();
  let shown = 0;
  $$(".dish").forEach(d => {
    const ok = (active === "all" || d.dataset.status === active) && (!q || d.dataset.text.includes(q));
    d.classList.toggle("hidden", !ok);
    if (ok) shown++;
  });
  $("#no-match")?.classList.toggle("hidden", shown > 0);
}

function showResult(r) {
  const out = $("#results");
  if (!r) return;
  if (r.kind === "product") {
    out.innerHTML = renderProduct(r);
  } else if (r.kind === "text") {
    out.innerHTML = renderText(r);
  } else if (r.kind === "notfound") {
    out.innerHTML = `<p class="rounded bg-amber-100 text-amber-900 px-4 py-3">Barcode ${esc(r.code)} was read correctly but is not in Open Food Facts database. Check the pack or ask staff.</p>`;
  } else if (r.kind === "menu") {
    out.innerHTML = renderMenu(r);
    const first = $('.filter[data-filter="all"]');
    if (first) first.classList.add("bg-ink", "text-white");
  } else {
    out.innerHTML = `<p class="rounded bg-white p-4 shadow-sm text-sm">Scan completed.</p>`;
  }
  out.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* Event delegation for dynamic controls */
document.addEventListener("click", async e => {
  const f = e.target.closest(".filter");
  if (f) {
    $$(".filter").forEach(b => b.classList.remove("bg-ink", "text-white"));
    f.classList.add("bg-ink", "text-white");
    applyFilter();
  }
  const n = e.target.closest(".nutri");
  if (n) {
    const dishName = n.dataset.dish;
    if (!dishName) return;
    const out = n.closest("article")?.querySelector(".nutri-out");
    if (!out) return;
    out.textContent = "Looking up nutrition...";
    try {
      const res = await fetch("/api/dish-info?name=" + encodeURIComponent(dishName));
      const j = await res.json();
      if (j.found && j.nutrition && j.nutrition.length) {
        out.innerHTML = `<span class="font-medium">Match: ${esc(j.name)}.</span> Per 100g: ` +
          j.nutrition.map(x => `${esc(x.label)} ${x.value}${esc(x.unit)}`).join(", ");
      } else if (j.found) {
        out.textContent = `Match found (${j.name}) but detailed nutrition numbers are not available.`;
      } else {
        out.textContent = "No match in Open Food Facts database. Restaurant dishes are often missing.";
      }
    } catch {
      out.textContent = "Nutrition lookup failed. Check your connection.";
    }
  }
});
document.addEventListener("input", e => { if (e.target.id === "dish-search") applyFilter(); });

/* ------------------------------------------------------------ sending scans */
function setBusy(msg) {
  const busyEl = $("#busy");
  if (msg) {
    busyEl.classList.remove("hidden");
    busyEl.classList.add("flex");
    $("#busy-msg").textContent = msg;
  } else {
    busyEl.classList.add("hidden");
    busyEl.classList.remove("flex");
  }
  $$("#controls button").forEach(b => {
    if (b.id !== "cam-stop") {
      b.disabled = !!msg || (b.id === "scan-photo" && !chosen);
    }
  });
}

function showError(msg) {
  const el = $("#error");
  el.textContent = msg || "";
  el.classList.toggle("hidden", !msg);
}

async function sendScan(fd, busyMsg) {
  showError("");
  setBusy(busyMsg);
  try {
    const res = await fetch("/api/scan", { method: "POST", body: fd });
    let j;
    try {
      j = await res.json();
    } catch {
      if (res.status === 413) {
        showError("The uploaded file is too large (max 16 MB). Try a smaller photo.");
      } else {
        showError(`Server error (${res.status}). Check server logs or try again.`);
      }
      return null;
    }
    if (!j.ok) {
      showError(j.error || "Scan failed.");
      return j;
    }
    showResult(j);
    loadHistory();
    return j;
  } catch (err) {
    showError("Could not reach the SafeBite server. Check that the application is running.");
    console.error("Scan request error:", err);
  } finally {
    setBusy(null);
  }
}

/* shrink big phone photos before upload (faster, under the size limit) */
async function shrink(file, maxSide = 2200) {
  if (!file || file.size < 1.5 * 1024 * 1024) return file;
  try {
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    if (k >= 1) return file;
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * k);
    c.height = Math.round(bmp.height * k);
    const ctx = c.getContext("2d");
    ctx.drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise(r => c.toBlob(r, "image/jpeg", 0.90));
    if (!blob) return file;
    const name = file.name ? file.name.replace(/\.[^/.]+$/, ".jpg") : "photo.jpg";
    return new File([blob], name, { type: "image/jpeg" });
  } catch (e) {
    console.warn("Could not shrink image on client, uploading original:", e);
    return file;
  }
}

/* ------------------------------------------------------------ tabs */
function openTab(name) {
  $$(".tab").forEach(t => {
    const on = t.dataset.tab === name;
    t.setAttribute("aria-selected", on);
    t.classList.toggle("border-ink", on);
    t.classList.toggle("text-ink", on);
    t.classList.toggle("border-transparent", !on);
    t.classList.toggle("text-ink/60", !on);
  });
  $$("[data-panel]").forEach(p => p.classList.toggle("hidden", p.dataset.panel !== name));
  if (name !== "camera") stopCamera();
}
$$(".tab").forEach(t => t.addEventListener("click", () => openTab(t.dataset.tab)));

/* ------------------------------------------------------------ photo upload */
let chosen = null;
const drop = $("#drop"), fileInput = $("#file");

function choose(file) {
  if (!file) return;
  if (!file.type || !file.type.startsWith("image/")) {
    return showError("Please select an image file (PNG, JPG, WEBP, or BMP).");
  }
  showError("");
  chosen = file;
  const img = $("#preview");
  img.src = URL.createObjectURL(file);
  img.classList.remove("hidden");
  const sizeKb = (file.size / 1024).toFixed(1);
  const name = file.name || "pasted-photo.jpg";
  $("#preview-info").textContent = `${name} (${sizeKb} KB)`;
  $("#preview-box")?.classList.remove("hidden");
  $("#drop-prompt")?.classList.add("hidden");
  $("#scan-photo").disabled = false;
  fileInput.value = "";
}

function clearChosenPhoto() {
  chosen = null;
  fileInput.value = "";
  $("#preview").src = "";
  $("#preview-box")?.classList.add("hidden");
  $("#drop-prompt")?.classList.remove("hidden");
  $("#scan-photo").disabled = true;
  showError("");
}

// Click on dropzone triggers file picker unless clicking remove button
drop.addEventListener("click", e => {
  if (e.target.closest("#remove-photo")) {
    e.stopPropagation();
    clearChosenPhoto();
    return;
  }
  fileInput.click();
});

fileInput.addEventListener("change", () => {
  if (fileInput.files && fileInput.files.length) {
    choose(fileInput.files[0]);
  }
});

// Prevent browser from navigating away if file is dropped outside dropzone
window.addEventListener("dragover", e => e.preventDefault());
window.addEventListener("drop", e => e.preventDefault());

drop.addEventListener("dragenter", e => { e.preventDefault(); drop.classList.add("drag"); });
drop.addEventListener("dragover",  e => { e.preventDefault(); drop.classList.add("drag"); });
drop.addEventListener("dragleave", e => { e.preventDefault(); drop.classList.remove("drag"); });
drop.addEventListener("drop", e => {
  e.preventDefault();
  e.stopPropagation();
  drop.classList.remove("drag");
  const files = e.dataTransfer?.files;
  if (files && files.length) {
    choose(files[0]);
  }
});

// Paste anywhere in page
document.addEventListener("paste", e => {
  if (document.activeElement && (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "TEXTAREA")) {
    const hasImage = [...(e.clipboardData?.items || [])].some(it => it.type.startsWith("image/"));
    if (!hasImage) return; // normal text paste in input/textarea
  }
  const items = e.clipboardData?.items || [];
  let file = null;
  for (const item of items) {
    if (item.type.startsWith("image/")) {
      file = item.getAsFile();
      break;
    }
  }
  if (!file && e.clipboardData?.files?.length) {
    file = [...e.clipboardData.files].find(x => x.type.startsWith("image/"));
  }
  if (file) {
    openTab("photo");
    choose(file);
  }
});

$("#scan-photo").addEventListener("click", async () => {
  if (!chosen) return showError("Please choose a photo first.");
  setBusy("Preparing image...");
  try {
    const readyFile = await shrink(chosen);
    const fd = new FormData();
    let fname = chosen.name || "photo.jpg";
    if (!fname.includes(".")) fname += ".jpg";
    fd.append("image", readyFile, fname);
    await sendScan(fd, "Reading photo with OCR... Menus and text scans can take a few seconds.");
  } catch (err) {
    showError("Could not prepare image for scanning.");
    console.error(err);
    setBusy(null);
  }
});

/* ------------------------------------------------------------ barcode + text */
$("#scan-code").addEventListener("click", () => {
  const code = $("#code").value.trim();
  if (!code) return showError("Please enter a barcode number.");
  const fd = new FormData();
  fd.append("barcode", code);
  sendScan(fd, "Looking up the product in Open Food Facts...");
});
$("#code").addEventListener("keydown", e => { if (e.key === "Enter") $("#scan-code").click(); });

$("#scan-text").addEventListener("click", () => {
  const txt = $("#ingredients").value.trim();
  if (!txt) return showError("Please paste or type ingredients to check.");
  const fd = new FormData();
  fd.append("ingredients", txt);
  sendScan(fd, "Checking ingredients for allergens...");
});

/* ------------------------------------------------------------ live camera */
let stream = null, loopTimer = null, inflight = false;
const video = $("#cam");

function frameBlob(maxW, quality) {
  if (!video.videoWidth || !video.videoHeight) {
    return Promise.reject(new Error("Video not ready"));
  }
  const k = Math.min(1, maxW / video.videoWidth);
  const c = document.createElement("canvas");
  c.width = Math.round(video.videoWidth * k);
  c.height = Math.round(video.videoHeight * k);
  c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
  return new Promise(r => c.toBlob(r, "image/jpeg", quality));
}

async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } }
    });
  } catch {
    return showError("Camera unavailable. Allow camera access, and use https or localhost.");
  }
  showError("");
  video.srcObject = stream;
  try {
    await video.play();
  } catch (err) {
    console.warn("video.play error:", err);
  }
  $("#cam-start").classList.add("hidden");
  $("#cam-stop").classList.remove("hidden");
  $("#cam-capture").classList.remove("hidden");
  $("#scanline").classList.remove("hidden");
  loopTimer = setInterval(autoScan, 1400);
}

async function autoScan() {
  if (inflight || !video.videoWidth) return;
  inflight = true;
  try {
    const blob = await frameBlob(1280, 0.85);
    const fd = new FormData();
    fd.append("image", blob, "frame.jpg");
    fd.append("mode", "code");
    const res = await fetch("/api/scan", { method: "POST", body: fd });
    const j = await res.json();
    if (j.ok) {
      stopCamera();
      showResult(j);
      loadHistory();
    }
  } catch {
    /* try again on next tick */
  }
  inflight = false;
}

function stopCamera() {
  clearInterval(loopTimer);
  loopTimer = null;
  if (stream) {
    stream.getTracks().forEach(t => t.stop());
    stream = null;
  }
  video.srcObject = null;
  $("#cam-start")?.classList.remove("hidden");
  $("#cam-stop")?.classList.add("hidden");
  $("#cam-capture")?.classList.add("hidden");
  $("#scanline")?.classList.add("hidden");
}

$("#cam-start").addEventListener("click", startCamera);
$("#cam-stop").addEventListener("click", stopCamera);
$("#cam-capture").addEventListener("click", async () => {
  try {
    const blob = await frameBlob(2000, 0.90);
    stopCamera();
    const fd = new FormData();
    fd.append("image", blob, "capture.jpg");
    sendScan(fd, "Reading photo with OCR... This can take a few seconds.");
  } catch {
    showError("Camera capture failed. Please make sure the camera is running.");
  }
});

/* ------------------------------------------------------------ history */
async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const j = await res.json();
    if (!j.ok) return;
    const historyList = $("#history");
    if (!historyList) return;
    historyList.innerHTML = (j.items && j.items.length) ? j.items.map(i => {
      const st = getStatus(i.status);
      return `
        <li class="flex gap-2 items-start py-1 border-b border-ink/5 last:border-none">
          <span class="mt-1.5 w-3 h-3 rounded-full shrink-0 ${st.dot}"></span>
          <span class="flex-1 min-w-0">
            <span class="font-medium block truncate">${esc(i.label)}</span>
            ${(i.allergens_found && i.allergens_found.length) ? `<span class="text-xs text-stop font-medium">${esc(i.allergens_found.join(", "))}</span>` : ""}
          </span>
        </li>`;
    }).join("")
    : `<li class="text-ink/60 text-xs py-2">Nothing flagged yet. Flagged scans will appear here.</li>`;
  } catch (err) {
    console.warn("Could not load history:", err);
  }
}

$("#clear-history").addEventListener("click", async () => {
  if (confirm("Clear your scan history? SOS will no longer list these items.")) {
    await fetch("/api/history", { method: "DELETE" });
    loadHistory();
  }
});

/* ------------------------------------------------------------ SOS */
$("#sos").addEventListener("click", async () => {
  if (!confirm("Send your emergency ID card to your emergency contact now?")) return;
  const msg = $("#sos-msg");
  msg.className = "mt-4 text-sm font-medium";
  msg.textContent = "Sending emergency alert...";
  try {
    const res = await fetch("/api/sos", { method: "POST" });
    const j = await res.json();
    msg.textContent = j.message || (j.sent ? "Emergency card sent successfully." : "Could not send emergency card.");
    msg.className = "mt-4 text-sm font-semibold " + (j.sent ? "text-go" : "text-amber-700");
  } catch {
    msg.textContent = "Network error. Call your emergency contact or local emergency number directly.";
    msg.className = "mt-4 text-sm font-semibold text-stop";
  }
});

openTab("photo");
loadHistory();
