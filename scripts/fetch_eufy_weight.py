#!/usr/bin/env python3
"""Fetch latest weight from Eufy Life private API and write a JSON snapshot."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = os.getenv("EUFY_API_BASE", "https://home-api.eufylife.com/v1").rstrip("/")
LOGIN_PATH = os.getenv("EUFY_LOGIN_PATH", "/user/v2/email/login")
DEVICES_PATH = os.getenv("EUFY_DEVICES_PATH", "/device/")
DATA_PATH_TEMPLATE = os.getenv("EUFY_DATA_PATH_TEMPLATE", "/device/{device_id}/data")
CATEGORY = os.getenv("EUFY_CATEGORY", "Health")
CLIENT_ID = os.getenv("EUFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EUFY_CLIENT_SECRET")
OUT_PATH = Path(os.getenv("WEIGHT_OUTPUT_PATH", "public/data/weight.json"))
FORCE_DEVICE_ID = os.getenv("EUFY_DEVICE_ID")
TIMEOUT = int(os.getenv("EUFY_TIMEOUT_SECONDS", "20"))
TARGET_WEIGHT_KG_RAW = os.getenv("TARGET_WEIGHT_KG")


def _request_json(method: str, path: str, headers: dict[str, str] | None = None, payload: dict[str, Any] | None = None) -> Any:
    url = f"{API_BASE}{path}"
    body = None
    req_headers: dict[str, str] = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url=url, method=method, data=body, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {err.code} {url}: {detail[:250]}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"Network error for {url}: {err}") from err

    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Invalid JSON from {url}") from err


def _extract_token(login_json: Any) -> str:
    candidates: list[Any] = []
    if isinstance(login_json, dict):
        candidates.extend([
            login_json.get("access_token"),
            login_json.get("token"),
        ])
        data = login_json.get("data")
        if isinstance(data, dict):
            candidates.extend([
                data.get("access_token"),
                data.get("token"),
                data.get("auth_token"),
            ])

    for token in candidates:
        if isinstance(token, str) and token:
            return token
    raise RuntimeError("Login response did not include an access token")


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


def _parse_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            ts /= 1000.0
        return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        if v.isdigit():
            return _parse_time(int(v))
        try:
            parsed = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            return None
    return None


def _to_kg(weight: float, unit: str | None) -> float:
    if not unit:
        return weight

    u = unit.strip().lower()
    if u in {"kg", "kgs", "kilogram", "kilograms"}:
        return weight
    if u in {"lb", "lbs", "pound", "pounds"}:
        return weight * 0.45359237
    if u in {"g", "gram", "grams"}:
        return weight / 1000.0
    if u in {"jin"}:
        return weight * 0.5
    return weight


def _pick_scale_device(devices_json: Any) -> dict[str, Any]:
    devices: list[dict[str, Any]] = []
    if isinstance(devices_json, list):
        devices = [d for d in devices_json if isinstance(d, dict)]
    elif isinstance(devices_json, dict):
        for key in ("data", "devices", "list", "items"):
            node = devices_json.get(key)
            if isinstance(node, list):
                devices = [d for d in node if isinstance(d, dict)]
                break

    if not devices:
        raise RuntimeError("No devices found in response")

    if FORCE_DEVICE_ID:
        for d in devices:
            did = d.get("id") or d.get("device_id") or d.get("deviceId")
            if str(did) == FORCE_DEVICE_ID:
                return d
        raise RuntimeError(f"EUFY_DEVICE_ID={FORCE_DEVICE_ID} was not found")

    scored: list[tuple[int, dict[str, Any]]] = []
    for d in devices:
        texts = " ".join(str(v).lower() for v in d.values() if isinstance(v, str))
        score = 0
        if "scale" in texts:
            score += 4
        if "health" in texts:
            score += 2
        if "body" in texts:
            score += 1
        scored.append((score, d))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _extract_latest_weight(data_json: Any) -> tuple[float, str | None]:
    best_weight: float | None = None
    best_time: str | None = None

    time_keys = ("time", "timestamp", "measureTime", "measuredAt", "created_at", "createdAt", "date")
    weight_keys = ("weight", "weight_kg", "weightKg", "body_weight", "bodyWeight")
    unit_keys = ("unit", "weight_unit", "weightUnit")

    for node in _iter_dicts(data_json):
        found_weight = None
        for key in weight_keys:
            value = node.get(key)
            if isinstance(value, (int, float)):
                found_weight = float(value)
                break
            if isinstance(value, str):
                try:
                    found_weight = float(value)
                    break
                except ValueError:
                    pass

        if found_weight is None:
            continue

        unit = None
        for key in unit_keys:
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                unit = val
                break

        time_iso = None
        for key in time_keys:
            time_iso = _parse_time(node.get(key))
            if time_iso:
                break

        weight_kg = _to_kg(found_weight, unit)
        if best_weight is None:
            best_weight = weight_kg
            best_time = time_iso
            continue

        if time_iso and (best_time is None or time_iso > best_time):
            best_weight = weight_kg
            best_time = time_iso

    if best_weight is None:
        raise RuntimeError("Could not find a weight value in device data")

    return best_weight, best_time


def _read_previous_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        return {}
    except (OSError, json.JSONDecodeError):
        return {}


def _to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _get_target_weight_kg() -> float:
    if TARGET_WEIGHT_KG_RAW is None:
        return 55.0
    value = TARGET_WEIGHT_KG_RAW.strip()
    if not value:
        return 55.0
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError("TARGET_WEIGHT_KG must be a number") from exc


def main() -> int:
    email = os.getenv("EUFY_EMAIL")
    password = os.getenv("EUFY_PASSWORD")
    if not email or not password or not CLIENT_ID or not CLIENT_SECRET:
        print("EUFY_EMAIL, EUFY_PASSWORD, EUFY_CLIENT_ID and EUFY_CLIENT_SECRET are required", file=sys.stderr)
        return 1

    login_payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "email": email,
        "password": password,
    }
    login_headers = {
        "category": CATEGORY,
    }

    login_json = _request_json("POST", LOGIN_PATH, headers=login_headers, payload=login_payload)
    token = _extract_token(login_json)

    api_headers = {
        "category": CATEGORY,
        "token": token,
    }

    devices_json = _request_json("GET", DEVICES_PATH, headers=api_headers)
    device = _pick_scale_device(devices_json)
    device_id = device.get("id") or device.get("device_id") or device.get("deviceId")
    if not device_id:
        raise RuntimeError("Selected device does not include an id")

    data_path = DATA_PATH_TEMPLATE.format(device_id=urllib.parse.quote(str(device_id), safe=""))
    data_json = _request_json("GET", data_path, headers=api_headers)

    weight_kg, measured_at = _extract_latest_weight(data_json)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    previous = _read_previous_snapshot(OUT_PATH)
    previous_initial = _to_float(previous.get("initialWeightKg"))
    initial_weight_kg = previous_initial if previous_initial is not None else weight_kg
    target_weight_kg = _get_target_weight_kg()

    payload = {
        "source": "eufy",
        "weightKg": round(weight_kg, 1),
        "targetWeightKg": round(target_weight_kg, 1),
        "initialWeightKg": round(initial_weight_kg, 1),
        "measuredAt": measured_at,
        "updatedAt": now_iso,
        "status": "ok",
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = OUT_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(OUT_PATH)

    print(f"Wrote {OUT_PATH} with {payload['weightKg']} kg")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"fetch_eufy_weight failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
