"""Bounded CSV imports, CAN decoding, and prediction comparisons."""

import csv
import hashlib
import io
import json
import math
import re
import struct
from collections import Counter
from itertools import pairwise

CHANNELS = {
    "throttle_variation": ("variation", 0, None),
    "brake_usage_pct": ("%", 0, 100),
    "energy_wh_km": ("Wh/km", 0, None),
    "regen_efficiency": ("fraction", 0, 1),
    "jerk_m_s3": ("m/s²/s", None, None),
    "speed_kph": ("km/h", 0, None),
    "pack_temp_c": ("°C", -80, 150),
    "pack_current_a": ("A", None, None),
    "pack_voltage_v": ("V", 0, None),
}
CAN_PROFILE = {
    0x300: ("throttle_variation", "brake_usage_pct"),
    0x301: ("energy_wh_km", "regen_efficiency"),
    0x302: ("jerk_m_s3", None),
}
LABEL_COLUMNS = {"expected_label", "predicted_label"}


def finite_number(value, description):
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{description} must be a number.") from None
    if not math.isfinite(number):
        raise ValueError(f"{description} must be finite.")
    if abs(number) > 1e100:
        raise ValueError(
            f"{description} exceeds the supported numeric magnitude (1e100)."
        )
    return number


def decode_can(identifier, payload):
    if isinstance(identifier, str):
        try:
            identifier = (
                int(identifier, 0)
                if identifier.lower().startswith("0x")
                else int(identifier, 16)
            )
        except ValueError:
            raise ValueError("CAN ID must be hexadecimal, for example 0x300.") from None
    if identifier not in CAN_PROFILE:
        raise ValueError(
            "Unknown CAN ID. The driver profile supports 0x300, 0x301, and 0x302."
        )
    if not isinstance(payload, str) or not re.fullmatch(
        r"[0-9a-fA-F]{16}", payload.replace(" ", "")
    ):
        raise ValueError("CAN payload must contain exactly eight bytes in hexadecimal.")
    values = struct.unpack("<ff", bytes.fromhex(payload))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("CAN payload contains a non-finite float.")
    return {
        channel: value
        for channel, value in zip(CAN_PROFILE[identifier], values)
        if channel
    }


def label_audit(rows):
    labeled = [
        row
        for row in rows
        if row.get("expected_label") is not None
        and row.get("predicted_label") is not None
    ]
    counts = Counter((r["expected_label"], r["predicted_label"]) for r in labeled)
    mismatches = [
        {
            "time_ms": r["time_ms"],
            "expected": r["expected_label"],
            "predicted": r["predicted_label"],
        }
        for r in labeled
        if r["expected_label"] != r["predicted_label"]
    ]
    return {
        "compared": len(labeled),
        "mismatches": mismatches,
        "accuracy": (len(labeled) - len(mismatches)) / len(labeled)
        if labeled
        else None,
        "confusion": [
            {"expected": a, "predicted": b, "count": count}
            for (a, b), count in sorted(counts.items())
        ],
    }


def parse_trace(name, content):
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError("Recording name must contain 1 to 100 characters.")
    if (
        not isinstance(content, str)
        or not content.strip()
        or len(content.encode()) > 3 * 1024 * 1024
    ):
        raise ValueError("Provide a nonempty CSV recording up to 3 MiB.")
    try:
        reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), strict=True)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or any(not f for f in fields):
            raise ValueError("CSV column names must be nonempty and unique.")
        if "time_ms" not in fields:
            raise ValueError("CSV requires a time_ms column.")
        mode = "can" if {"can_id", "data_hex"} <= set(fields) else "signals"
        channels = (
            []
            if mode == "can"
            else [f for f in fields if f != "time_ms" and f not in LABEL_COLUMNS]
        )
        if mode == "signals" and (not channels or len(channels) > 12):
            raise ValueError("Signal CSV requires 1 to 12 numeric channels.")
        if any(
            len(f) > 60 or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", f)
            for f in channels
        ):
            raise ValueError("Channel names must be identifiers up to 60 characters.")
        rows, warnings, last_values, last_times = [], [], {}, {}
        previous = -1.0
        for index, source in enumerate(reader, 2):
            if len(rows) >= 20000:
                raise ValueError("Recordings may contain at most 20,000 rows.")
            if None in source or any(value is None for value in source.values()):
                raise ValueError(
                    f"Row {index}: column count does not match the header."
                )
            timestamp = finite_number(source["time_ms"], f"Row {index} time_ms")
            if (
                timestamp < 0
                or timestamp > 1e12
                or timestamp < previous
                or (mode == "signals" and timestamp == previous)
            ):
                order = "nondecreasing" if mode == "can" else "strictly increasing"
                raise ValueError(
                    f"Row {index}: time_ms must be between 0 and 1e12 and {order}."
                )
            previous = timestamp
            if mode == "can":
                try:
                    decoded = decode_can(source["can_id"], source["data_hex"])
                except ValueError as error:
                    raise ValueError(f"Row {index}: {error}") from None
                last_values.update(decoded)
                last_times.update({key: timestamp for key in decoded})
                row = {
                    "time_ms": timestamp,
                    "values": dict(last_values),
                    "frame": {
                        "can_id": source["can_id"],
                        "data_hex": source["data_hex"],
                        "updated": list(decoded),
                        "age_ms": {
                            key: timestamp - last_times[key] for key in last_values
                        },
                    },
                }
            else:
                values = {
                    channel: finite_number(source[channel], f"Row {index} {channel}")
                    for channel in channels
                }
                row = {"time_ms": timestamp, "values": values}
                for key in LABEL_COLUMNS:
                    if key in source and source[key].strip():
                        if len(source[key]) > 80:
                            raise ValueError(
                                f"Row {index}: labels must be at most 80 characters."
                            )
                        row[key] = source[key].strip()
            for channel, value in row["values"].items():
                unit, low, high = CHANNELS.get(channel, ("unitless", None, None))
                outside_range = (low is not None and value < low) or (
                    high is not None and value > high
                )
                if outside_range and len(warnings) < 100:
                    warnings.append(
                        {
                            "row": index,
                            "channel": channel,
                            "value": value,
                            "message": f"Outside the declared {unit} range.",
                        }
                    )
            rows.append(row)
    except csv.Error as error:
        raise ValueError(f"Invalid CSV: {error}") from None
    if not rows:
        raise ValueError("The recording contains no data rows.")
    channels = sorted({key for row in rows for key in row["values"]})
    summary = []
    for channel in channels:
        values = [r["values"][channel] for r in rows if channel in r["values"]]
        unit, low, high = CHANNELS.get(channel, ("unitless", None, None))
        summary.append(
            {
                "name": channel,
                "unit": unit,
                "min": min(values),
                "max": max(values),
                "mean": sum(value / len(values) for value in values),
                "samples": len(values),
                "range": [low, high],
            }
        )
    intervals = [b["time_ms"] - a["time_ms"] for a, b in pairwise(rows)]
    return {
        "name": name.strip(),
        "mode": mode,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "rows": rows,
        "channels": summary,
        "duration_ms": rows[-1]["time_ms"] - rows[0]["time_ms"],
        "interval_ms": {"min": min(intervals), "max": max(intervals)}
        if intervals
        else None,
        "warnings": warnings,
        "audit": label_audit(rows),
        "contract": "Driver float-pairs v1, little-endian IEEE 754"
        if mode == "can"
        else "Numeric signal CSV v1",
    }


def canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
