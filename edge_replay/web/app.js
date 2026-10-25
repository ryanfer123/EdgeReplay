"use strict";
const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const format = (value) =>
  value === undefined
    ? "—"
    : Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
const label = (name) => name.replaceAll("_", " ");
let recording = null,
  index = 0,
  elapsed = 0,
  playing = false,
  raf = null,
  lastFrame = null;
let chartCache = null;
async function api(path, data) {
  const response = await fetch(
    path,
    data === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
  );
  const body = await response.json();
  if (!response.ok)
    throw new Error(body.error || `Request failed (${response.status}).`);
  return body;
}
function notice(message, error = false) {
  $("notice").textContent = message;
  $("notice").hidden = !message;
  $("notice").classList.toggle("error", error);
}
function pause() {
  playing = false;
  lastFrame = null;
  if (raf !== null) cancelAnimationFrame(raf);
  raf = null;
  $("play-label").textContent = "Play";
  $("play").setAttribute("aria-label", "Play recording");
}
function currentChannel() {
  return (
    recording.channels.find(
      (channel) => channel.name === $("channel-select").value,
    ) || recording.channels[0]
  );
}
function startTime() {
  return recording.rows[0].time_ms;
}
function timeIndex(time) {
  let low = 0,
    high = recording.rows.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (recording.rows[mid].time_ms <= time) low = mid + 1;
    else high = mid;
  }
  return Math.max(0, low - 1);
}
function seekTo(time) {
  elapsed = Math.max(0, Math.min(recording.duration_ms, time));
  index = timeIndex(startTime() + elapsed);
  renderPosition();
}
function inspectIndex(next) {
  pause();
  index = Math.max(0, Math.min(recording.rows.length - 1, next));
  elapsed = recording.rows[index].time_ms - startTime();
  renderPosition();
}
function frame(now) {
  if (!playing || !recording) return;
  if (lastFrame !== null)
    elapsed += Math.min(1000, now - lastFrame) * Number($("speed").value);
  lastFrame = now;
  if (elapsed >= recording.duration_ms) {
    elapsed = recording.duration_ms;
    index = recording.rows.length - 1;
    renderPosition();
    pause();
    return;
  }
  index = timeIndex(startTime() + elapsed);
  renderPosition();
  raf = requestAnimationFrame(frame);
}
function play() {
  if (!recording) return;
  if (playing) {
    pause();
    return;
  }
  if (elapsed >= recording.duration_ms) {
    elapsed = 0;
    index = 0;
  }
  playing = true;
  lastFrame = null;
  $("play-label").textContent = "Pause";
  $("play").setAttribute("aria-label", "Pause recording");
  raf = requestAnimationFrame(frame);
}
function buildChart() {
  const channel = currentChannel(),
    rows = recording.rows;
  const min = channel.min,
    max = channel.max,
    padding = (max - min || Math.abs(max) || 1) * 0.13;
  const low = min - padding,
    high = max + padding;
  const x = (t) =>
    65 +
    (recording.duration_ms ? (t - startTime()) / recording.duration_ms : 0) *
      900;
  const y = (value) => 224 - ((value - low) / (high - low)) * 198;
  // Downsample only the drawing; inspection and exports retain every sample.
  const stride = Math.max(1, Math.ceil(rows.length / 1500));
  const sampled = rows
    .filter((row, i) => i % stride === 0 || i === rows.length - 1)
    .filter((row) => row.values[channel.name] !== undefined);
  const points = sampled.map(
    (row) =>
      `${x(row.time_ms).toFixed(2)},${y(row.values[channel.name]).toFixed(2)}`,
  );
  const d = points.length ? "M " + points.join(" L ") : "";
  const area = points.length
    ? `${d} L ${x(sampled.at(-1).time_ms)} 224 L ${x(sampled[0].time_ms)} 224 Z`
    : "";
  let grid = "";
  for (let i = 0; i < 5; i++) {
    const value = low + ((high - low) * i) / 4,
      yy = y(value);
    grid += `<line class="grid-line" x1="65" x2="965" y1="${yy}" y2="${yy}"/><text x="52" y="${yy + 3}" text-anchor="end">${esc(format(value))}</text>`;
  }
  for (let i = 0; i <= 5; i++) {
    const xx = 65 + i * 180;
    grid += `<text x="${xx}" y="253" text-anchor="middle">${((recording.duration_ms * i) / 5000).toFixed(1)} s</text>`;
  }
  const events = recording.audit.mismatches
    .slice(0, 100)
    .map(
      (event) =>
        `<circle class="event" cx="${x(event.time_ms)}" cy="234" r="3"><title>Label disagreement at ${event.time_ms} ms</title></circle>`,
    )
    .join("");
  $("signal-chart").innerHTML =
    `<title>${esc(label(channel.name))} over time in ${esc(channel.unit)}</title>${grid}<path class="area" d="${area}"/><path class="wave" d="${d}"/>${events}<line class="playhead" id="playhead" x1="65" x2="65" y1="20" y2="224"/><circle class="point" id="chart-point" cx="65" cy="224" r="5"/>`;
  chartCache = { x, y };
  renderPosition();
  document.dispatchEvent(new CustomEvent("edge:chart"));
}
function renderPosition() {
  if (!recording) return;
  const row = recording.rows[index],
    channel = currentChannel(),
    value = row.values[channel.name];
  $("current-value").textContent = format(value);
  $("current-unit").textContent = channel.unit;
  $("seek").value = elapsed;
  $("position").textContent = (elapsed / 1000).toFixed(3);
  $("inspector-time").textContent = `${format(row.time_ms)} ms`;
  $("sample-position").textContent =
    `Sample ${index + 1} of ${recording.rows.length}`;
  if (chartCache) {
    const xx = chartCache.x(startTime() + elapsed);
    $("playhead").setAttribute("x1", xx);
    $("playhead").setAttribute("x2", xx);
    $("chart-point").setAttribute("cx", xx);
    $("chart-point").setAttribute(
      "cy",
      value === undefined ? 224 : chartCache.y(value),
    );
    $("chart-point").setAttribute(
      "visibility",
      value === undefined ? "hidden" : "visible",
    );
  }
  $("live-values").innerHTML = recording.channels
    .map(
      (c) =>
        `<div class="live-row"><div><span class="channel-name">${esc(label(c.name))}</span>${row.frame && c.name in row.frame.age_ms ? `<span class="age">${format(row.frame.age_ms[c.name])} ms since update</span>` : ""}</div><strong>${esc(format(row.values[c.name]))}<small>${esc(c.unit)}</small></strong></div>`,
    )
    .join("");
  $("frame-details").hidden = !row.frame;
  if (row.frame)
    $("frame-details").innerHTML =
      `Frame <strong>${esc(row.frame.can_id)}</strong><code>${esc(row.frame.data_hex)}</code>Updated: ${row.frame.updated.map(esc).join(", ")}`;
}
async function refreshList(preferred) {
  const data = await api("/api/recordings");
  $("recording-select").innerHTML =
    '<option value="">Choose a recording</option>' +
    data.recordings
      .map((r) => `<option value="${esc(r.id)}">${esc(r.name)}</option>`)
      .join("");
  if (preferred) $("recording-select").value = preferred;
  return data.recordings;
}
function renderRecording() {
  pause();
  elapsed = 0;
  index = timeIndex(startTime());
  for (const id of ["signal-workspace", "contracts", "predictions"])
    $(id).hidden = false;
  $("empty").hidden = true;
  $("export-csv").disabled = false;
  $("export-json").disabled = false;
  $("recording-facts").textContent =
    `${recording.rows.length.toLocaleString()} samples · ${recording.channels.length} channels · ${(recording.duration_ms / 1000).toFixed(1)} s`;
  $("mode-tag").textContent =
    recording.mode === "can" ? "Decoded CAN frames" : "Numeric signals";
  $("recording-context").textContent = recording.name;
  $("channel-select").innerHTML = recording.channels
    .map((c) => `<option value="${esc(c.name)}">${esc(label(c.name))}</option>`)
    .join("");
  const speedChannel = recording.channels.find((c) => c.name === "speed_kph");
  if (speedChannel) $("channel-select").value = speedChannel.name;
  $("seek").max = Math.max(1, recording.duration_ms);
  $("seek").step = "any";
  $("duration").textContent = (recording.duration_ms / 1000).toFixed(3);
  $("summary").innerHTML = [
    [
      "Samples",
      recording.rows.length.toLocaleString(),
      "Every imported row retained",
    ],
    ["Channels", recording.channels.length, "Selectable signal traces"],
    [
      "Sample intervals",
      recording.interval_ms
        ? `${format(recording.interval_ms.min)}–${format(recording.interval_ms.max)} ms`
        : "Single sample",
      "CAN bursts retain source order",
    ],
    [
      "Source fingerprint",
      recording.sha256.slice(0, 12),
      "SHA256 included in session export",
    ],
  ]
    .map(
      ([title, value, note]) =>
        `<div class="summary-item"><span>${esc(title)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></div>`,
    )
    .join("");
  $("channel-table").innerHTML = recording.channels
    .map(
      (c) =>
        `<tr><td>${esc(c.name)}</td><td>${esc(c.unit)}</td><td>${esc(format(c.min))}</td><td>${esc(format(c.max))}</td><td>${esc(format(c.mean))}</td><td>${c.samples}</td></tr>`,
    )
    .join("");
  $("warning-count").textContent = recording.warnings.length
    ? `${recording.warnings.length} range notices`
    : "No declared-range notices";
  $("warnings").innerHTML = recording.warnings.length
    ? `<div class="warning-list"><h3>Check the source units</h3><ul>${recording.warnings
        .slice(0, 12)
        .map(
          (w) =>
            `<li>CSV row ${w.row}: ${esc(w.channel)} = ${esc(format(w.value))}. ${esc(w.message)}</li>`,
        )
        .join(
          "",
        )}</ul>${recording.warnings.length > 12 ? "<p>First 12 shown. Session JSON contains up to 100 notices.</p>" : ""}</div>`
    : "";
  const audit = recording.audit;
  $("audit").innerHTML = audit.compared
    ? `<div class="audit-summary"><div><strong>${audit.compared}</strong><span>Compared label pairs</span></div><div><strong>${audit.mismatches.length}</strong><span>Disagreements</span></div><div><strong>${(audit.accuracy * 100).toFixed(1)}%</strong><span>Imported label agreement</span></div><p>These are expected and predicted labels in your CSV. They are not fresh model inference, an independent test set, or evidence of deployment quality.</p></div><div class="table-wrap"><table><thead><tr><th>Time</th><th>Expected label</th><th>Predicted label</th><th>Inspect</th></tr></thead><tbody>${
        audit.mismatches.length
          ? audit.mismatches
              .slice(0, 100)
              .map(
                (event) =>
                  `<tr><td>${format(event.time_ms)} ms</td><td>${esc(event.expected)}</td><td>${esc(event.predicted)}</td><td><button class="event-button" data-time="${event.time_ms}">Jump to sample</button></td></tr>`,
              )
              .join("")
          : '<tr><td colspan="4">No disagreements among the imported label pairs.</td></tr>'
      }</tbody></table></div>`
    : '<div class="audit-empty"><h3>No prediction labels attached.</h3><p>Add <code>expected_label</code> and <code>predicted_label</code> columns to a signal CSV to compare your model output against recorded labels. EdgeReplay will mark disagreements on the timeline. It does not run a model or invent an accuracy score.</p></div>';
  buildChart();
}
async function loadRecording(id) {
  recording = await api("/api/recordings/" + encodeURIComponent(id));
  renderRecording();
  $("recording-select").value = id;
}
async function sample(path, name) {
  try {
    const response = await fetch(path);
    if (!response.ok) throw new Error("Sample could not be loaded.");
    const csv = await response.text();
    recording = await api("/api/recordings", { name, csv });
    await refreshList(recording.id);
    renderRecording();
    notice(
      "Synthetic fixture loaded. Replay illustrates the workflow; it is not a real vehicle recording.",
    );
  } catch (error) {
    notice(error.message, true);
  }
}
$("load-demo").addEventListener("click", () =>
  sample("/demo.csv", "Synthetic drive · 60 seconds"),
);
$("load-can").addEventListener("click", () =>
  sample("/example-can.csv", "Synthetic CAN · driver feature pairs"),
);
$("recording-select").addEventListener("change", async () => {
  if (!$("recording-select").value) return;
  try {
    await loadRecording($("recording-select").value);
    notice("Saved recording loaded.");
  } catch (error) {
    notice(error.message, true);
  }
});
$("channel-select").addEventListener("change", buildChart);
$("play").addEventListener("click", play);
$("restart").addEventListener("click", () => {
  pause();
  seekTo(0);
});
$("step").addEventListener("click", () => inspectIndex(index + 1));
$("seek").addEventListener("input", () => {
  pause();
  seekTo(Number($("seek").value));
});
$("audit").addEventListener("click", (event) => {
  const button = event.target.closest("[data-time]");
  if (!button) return;
  pause();
  seekTo(Number(button.dataset.time) - startTime());
  $("signal-workspace").scrollIntoView({ behavior: "instant", block: "start" });
});
for (const [id, query] of [
  ["export-csv", "format=csv"],
  ["export-json", "download=1"],
])
  $(id).addEventListener("click", () => {
    if (!recording) return;
    const anchor = document.createElement("a");
    anchor.href = `/api/recordings/${encodeURIComponent(recording.id)}?${query}`;
    anchor.download = "";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    notice(
      "Export requested. The recording and source fingerprint remain in your saved session.",
    );
  });
$("open-import").addEventListener("click", () => {
  $("import-error").hidden = true;
  $("import-dialog").showModal();
});
for (const button of document.querySelectorAll(".close-dialog"))
  button.addEventListener("click", () => $("import-dialog").close());
$("csv-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 3 * 1024 * 1024) {
    $("import-error").textContent = "File exceeds 3 MiB.";
    $("import-error").hidden = false;
    return;
  }
  $("csv-text").value = await file.text();
  if (!$("recording-name").value)
    $("recording-name").value = file.name.replace(/\.csv$/i, "");
});
$("import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("save-import").disabled = true;
  $("import-error").hidden = true;
  try {
    recording = await api("/api/recordings", {
      name: $("recording-name").value,
      csv: $("csv-text").value,
    });
    await refreshList(recording.id);
    renderRecording();
    $("import-dialog").close();
    notice(`Imported “${recording.name}”. Recording saved locally.`);
  } catch (error) {
    $("import-error").textContent = error.message;
    $("import-error").hidden = false;
  } finally {
    $("save-import").disabled = false;
  }
});
const visibility = () => {
  if (document.hidden) pause();
};
document.addEventListener("visibilitychange", visibility);
window.addEventListener(
  "pagehide",
  () => {
    pause();
    document.removeEventListener("visibilitychange", visibility);
  },
  { once: true },
);
(async () => {
  try {
    const records = await refreshList();
    if (records.length) await loadRecording(records[0].id);
  } catch (error) {
    notice(`Could not load the workspace: ${error.message}`, true);
  }
})();
