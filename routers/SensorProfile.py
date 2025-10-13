from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional
from datetime import datetime
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


def _normalize_updates_node(updates: Any) -> List[Dict[str, Any]]:
    """
    Normalize a Firebase node into a list of update dicts.

    Handles:
    - dict of push-keys -> update dicts  -> returns list(update dicts)
    - single update dict -> returns [dict]
    - list -> returns list
    - None/other -> returns []
    """
    if updates is None:
        return []
    if isinstance(updates, list):
        return updates
    if isinstance(updates, dict):
        # If values are dicts, assume push-keys -> update dicts
        if any(isinstance(v, dict) for v in updates.values()):
            return list(updates.values())
        # Single update stored directly under sensor key
        return [updates]
    return []


def _sort_updates(updates: List[Dict[str, Any]], newest_first: bool = True) -> List[Dict[str, Any]]:
    try:
        return sorted(updates, key=lambda u: _parse_timestamp(u.get("timestamp")), reverse=newest_first)
    except Exception:
        return updates



@router.get("/EcoWatch/sensors/{sensor_id}/history")
async def get_sensor_history(sensor_id: str, limit: Optional[int] = Query(None, ge=1), sort: str = Query("desc", regex="^(asc|desc)$")):
    """
    Return full history for a single sensor_id.

    Query params same as /EcoWatch/sensors/history.
    """
    try:
        ref = db.reference("EcoWatch/sensors")
        node = ref.child(sensor_id).get()
        if node is None:
            raise HTTPException(status_code=404, detail="Sensor not found")

        updates = _normalize_updates_node(node)
        updates = _sort_updates(updates, newest_first=(sort == "desc"))
        if limit is not None:
            updates = updates[:limit]
        return {"sensor_id": sensor_id, "history": updates}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
