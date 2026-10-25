/* Serialize restorable recordings, not ephemeral IDs or derived model results. */
(() => {
  "use strict";
  const object = (value) =>
    value && typeof value === "object" && !Array.isArray(value);
  const KIND = "edge-replay-recording";
  const LIMIT = 3 * 1024 * 1024;
  const quote = (value) => {
    const text = String(value ?? "");
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  function restoreInput(payload) {
    if (!object(payload) || payload.kind !== KIND || payload.version !== 1)
      throw new Error(
        "This cloud copy is not a supported EdgeReplay recording.",
      );
    if (
      typeof payload.name !== "string" ||
      !payload.name.trim() ||
      payload.name.length > 100
    )
      throw new Error("The saved recording has an invalid name.");
    if (
      typeof payload.csv !== "string" ||
      !payload.csv.trim() ||
      new TextEncoder().encode(payload.csv).length > LIMIT
    )
      throw new Error(
        "The saved recording must contain CSV data no larger than 3 MiB.",
      );
    return { name: payload.name.trim(), csv: payload.csv };
  }
  function snapshot(recording) {
    if (
      !object(recording) ||
      !Array.isArray(recording.rows) ||
      !recording.rows.length
    )
      throw new Error("Load a recording before saving a cloud copy.");
    let fields, rows;
    if (recording.mode === "can") {
      fields = ["time_ms", "can_id", "data_hex"];
      rows = recording.rows.map((row) => {
        if (!object(row.frame))
          throw new Error(
            "The recording is missing its original CAN frame data.",
          );
        return [row.time_ms, row.frame.can_id, row.frame.data_hex];
      });
    } else if (
      recording.mode === "signals" &&
      Array.isArray(recording.channels)
    ) {
      const channels = recording.channels.map((channel) => channel.name);
      const labels = ["expected_label", "predicted_label"].filter((key) =>
        recording.rows.some((row) => key in row),
      );
      fields = ["time_ms", ...channels, ...labels];
      rows = recording.rows.map((row) => [
        row.time_ms,
        ...channels.map((key) => row.values[key]),
        ...labels.map((key) => row[key]),
      ]);
    } else throw new Error("The recording uses an unsupported input format.");
    const payload = {
      kind: KIND,
      version: 1,
      name: recording.name,
      csv:
        [fields, ...rows].map((row) => row.map(quote).join(",")).join("\r\n") +
        "\r\n",
    };
    restoreInput(payload);
    if (
      typeof recording.sha256 === "string" &&
      /^[a-f0-9]{64}$/i.test(recording.sha256)
    )
      payload.originalSourceSha256 = recording.sha256;
    return payload;
  }
  globalThis.EdgeReplayCloudAdapter = { snapshot, restoreInput };
})();
