from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from firebase_admin import db

router = APIRouter()


def _parse_timestamp(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts)
        except Exception:
            return datetime.min
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            try:
                return datetime.fromtimestamp(float(ts))
            except Exception:
                return datetime.min
    return datetime.min


def _normalize_node_to_latest(node: Any) -> Optional[Dict[str, Any]]:
    """
    Given a DB node for a sensor, return a single dict representing the latest update.
    Handles:
    - dict of push-keys -> update dicts  (returns newest by timestamp)
    - single update dict (returns it)
    - None -> None
    """
    if node is None:
        return None
    if isinstance(node, dict):
        # if values are dicts, assume push-keys -> updates
        if any(isinstance(v, dict) for v in node.values()):
            entries = [v for v in node.values() if isinstance(v, dict)]
            entries.sort(key=lambda e: _parse_timestamp(e.get("timestamp")), reverse=True)
            return entries[0] if entries else None
        # otherwise single update stored under key
        return node
    return None


@router.get("/EcoWatch/info/network-summary")
async def network_summary():
    """
    Return network summary:
    - average_signal_strength (for online sensors with numeric signal)
    - online_count, offline_count, total_sensors, offline_sensor_ids
    - area_info: if sensors have 'area' or 'region' field -> unique areas + counts;
    else if sensors have 'location' (lat/lon) -> bounding box + count_with_location
    - maintenance: next_maintenance_by_sensor (ISO), due_soon list (next 7 days)
    """
    try:
        ref = db.reference("EcoWatch/sensors")
        all_sensors = ref.get() or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    total = 0
    online_count = 0
    offline_ids: List[str] = []
    signal_values: List[float] = []
    areas: Dict[str, int] = {}
    loc_count = 0
    lats: List[float] = []
    lons: List[float] = []
    maintenance_next: Dict[str, str] = {}
    maintenance_due_soon: List[str] = []

    now = datetime.utcnow()
    maintenance_window = now + timedelta(days=7)
    MAINTENANCE_INTERVAL = timedelta(days=30)

    for sensor_id, node in all_sensors.items():
        latest = _normalize_node_to_latest(node)
        if not latest:
            continue
        total += 1

        # determine online/offline
        is_active = latest.get("isActive")
        status = (latest.get("status") or "").lower() if latest.get("status") else ""
        online = False
        if isinstance(is_active, bool):
            online = is_active
        elif status in ("online", "active"):
            online = True
        elif latest.get("signal_strength") is not None:
            # treat presence of signal as online if numeric and > 0
            try:
                s = float(latest.get("signal_strength"))
                online = s > -1000  # crude check
            except Exception:
                online = False

        if online:
            online_count += 1
        else:
            offline_ids.append(sensor_id)

        # collect signal strengths
        sig = latest.get("signal_strength")
        if sig is not None:
            try:
                signal_values.append(float(sig))
            except Exception:
                pass

        # area/region handling
        area = latest.get("area") or latest.get("region")
        if isinstance(area, str) and area.strip():
            areas[area] = areas.get(area, 0) + 1

        # location handling (optional)
        loc = latest.get("location") or latest.get("coords") or latest.get("coordinate")
        if isinstance(loc, dict):
            lat = loc.get("lat") or loc.get("latitude")
            lon = loc.get("lon") or loc.get("longitude") or loc.get("lng")
            try:
                latf = float(lat)
                lonf = float(lon)
                lats.append(latf)
                lons.append(lonf)
                loc_count += 1
            except Exception:
                pass

        # maintenance scheduling
        last_maint = latest.get("last_maintenance") or latest.get("maintenance") or latest.get("lastMaintenance")
        if last_maint:
            lm_dt = _parse_timestamp(last_maint)
            next_maint = lm_dt + MAINTENANCE_INTERVAL
        else:
            # if never maintained, schedule immediately
            next_maint = now
        maintenance_next[sensor_id] = next_maint.isoformat()
        if next_maint <= maintenance_window:
            maintenance_due_soon.append(sensor_id)

    avg_signal = None
    if signal_values:
        avg_signal = sum(signal_values) / len(signal_values)

    # area_info assembly
    area_info: Dict[str, Any] = {}
    if areas:
        area_info["type"] = "area_counts"
        area_info["unique_areas"] = len(areas)
        area_info["counts"] = areas
    elif loc_count > 0:
        area_info["type"] = "bounding_box"
        area_info["count_with_location"] = loc_count
        area_info["bbox"] = {
            "min_lat": min(lats),
            "max_lat": max(lats),
            "min_lon": min(lons),
            "max_lon": max(lons),
        }
    else:
        area_info["type"] = "unknown"
        area_info["message"] = "no area or location data available"

    return {
        "total_sensors": total,
        "online_count": online_count,
        "offline_count": len(offline_ids),
        "offline_sensor_ids": offline_ids,
        "average_signal_strength": avg_signal,
        "area_info": area_info,
        "maintenance": {
            "next_maintenance_by_sensor": maintenance_next,
            "due_soon": maintenance_due_soon,
            "recommended_interval_days": 30
        }
    }