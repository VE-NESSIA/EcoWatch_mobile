# # routers/SensorProfile.py
# from fastapi import APIRouter, HTTPException, Query
# from typing import Any, Dict, List, Optional
# from datetime import datetime
# from firebase_admin import db

# router = APIRouter()

# def _parse_timestamp(ts: Any) -> datetime:
#     if isinstance(ts, datetime):
#         return ts
#     if isinstance(ts, (int, float)):
#         try:
#             return datetime.fromtimestamp(ts)
#         except Exception:
#             return datetime.min
#     if isinstance(ts, str):
#         try:
#             return datetime.fromisoformat(ts)
#         except Exception:
#             try:
#                 return datetime.fromtimestamp(float(ts))
#             except Exception:
#                 return datetime.min
#     return datetime.min

# def _normalize_updates_node(updates: Any) -> List[Dict[str, Any]]:
#     """
#     Normalize a Firebase node into a list of update dicts.
#     Handles:
#     - dict of push-keys -> update dicts  -> returns list(update dicts)
#     - single update dict -> returns [dict]
#     - list -> returns list
#     - None/other -> returns []
#     """
#     if updates is None:
#         return []
#     if isinstance(updates, list):
#         return updates
#     if isinstance(updates, dict):
#         # If values are dicts, assume push-keys -> update dicts
#         if any(isinstance(v, dict) for v in updates.values()):
#             return list(updates.values())
#         # Single update stored directly under sensor key
#         return [updates]
#     return []

# def _sort_updates(updates: List[Dict[str, Any]], newest_first: bool = True) -> List[Dict[str, Any]]:
#     try:
#         return sorted(updates, key=lambda u: _parse_timestamp(u.get("timestamp")), reverse=newest_first)
#     except Exception:
#         return updates

# @router.get("/EcoWatch/sensors/{sensor_id}/history", tags=["Sensors"])
# async def get_sensor_history(
#     sensor_id: str, 
#     limit: Optional[int] = Query(None, ge=1, description="Maximum number of records to return"),
#     sort: str = Query("desc", regex="^(asc|desc)$", description="Sort order: 'asc' or 'desc'")
# ):
#     """
#     Return full history for a single sensor_id.
    
#     **Parameters:**
#     - `sensor_id`: The sensor identifier
#     - `limit`: Maximum number of records to return (optional)
#     - `sort`: Sort order - 'desc' for newest first (default), 'asc' for oldest first
    
#     **Example:**
#     - `/EcoWatch/sensors/SENSOR_001/history?limit=10&sort=desc`
#     """
#     try:
#         ref = db.reference("EcoWatch/sensors")
#         node = ref.child(sensor_id).get()
        
#         if node is None:
#             raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
        
#         updates = _normalize_updates_node(node)
#         updates = _sort_updates(updates, newest_first=(sort == "desc"))
        
#         if limit is not None:
#             updates = updates[:limit]
        
#         return {
#             "sensor_id": sensor_id,
#             "history": updates,
#             "total_records": len(updates),
#             "sort_order": sort
#         }
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching sensor history: {str(e)}")

# routers/SensorProfile.py
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

@router.get("/EcoWatch/sensors", tags=["Sensors"])
async def get_all_sensors(
    include_latest: bool = Query(True, description="Include latest reading for each sensor")
):
    """
    Get list of all sensors in the database.
    
    **Parameters:**
    - `include_latest`: If true, includes the most recent reading for each sensor
    
    **Returns:**
    - List of all sensor IDs with optional latest reading data
    
    **Example:**
    - `/EcoWatch/sensors`
    - `/EcoWatch/sensors?include_latest=false`
    """
    try:
        ref = db.reference("EcoWatch/sensors")
        all_sensors = ref.get()
        
        if all_sensors is None:
            return {
                "sensors": [],
                "total_count": 0,
                "message": "No sensors found in database"
            }
        
        sensor_list = []
        
        for sensor_id, sensor_data in all_sensors.items():
            sensor_info = {
                "sensor_id": sensor_id
            }
            
            if include_latest:
                # Get the latest update for this sensor
                updates = _normalize_updates_node(sensor_data)
                if updates:
                    sorted_updates = _sort_updates(updates, newest_first=True)
                    latest = sorted_updates[0]
                    sensor_info["latest_reading"] = latest
                    sensor_info["total_records"] = len(updates)
                else:
                    sensor_info["latest_reading"] = None
                    sensor_info["total_records"] = 0
            
            sensor_list.append(sensor_info)
        
        # Sort by sensor_id for consistent ordering
        sensor_list.sort(key=lambda x: x["sensor_id"])
        
        return {
            "sensors": sensor_list,
            "total_count": len(sensor_list),
            "include_latest": include_latest
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching sensors: {str(e)}")

@router.get("/EcoWatch/sensors/{sensor_id}/history", tags=["Sensors"])
async def get_sensor_history(
    sensor_id: str,
    limit: Optional[int] = Query(None, ge=1, description="Maximum number of records to return"),
    sort: str = Query("desc", regex="^(asc|desc)$", description="Sort order: 'asc' or 'desc'")
):
    """
    Return full history for a single sensor_id.
   
    **Parameters:**
    - `sensor_id`: The sensor identifier
    - `limit`: Maximum number of records to return (optional)
    - `sort`: Sort order - 'desc' for newest first (default), 'asc' for oldest first
   
    **Example:**
    - `/EcoWatch/sensors/SENSOR_001/history?limit=10&sort=desc`
    """
    try:
        ref = db.reference("EcoWatch/sensors")
        node = ref.child(sensor_id).get()
       
        if node is None:
            raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
       
        updates = _normalize_updates_node(node)
        updates = _sort_updates(updates, newest_first=(sort == "desc"))
       
        if limit is not None:
            updates = updates[:limit]
       
        return {
            "sensor_id": sensor_id,
            "history": updates,
            "total_records": len(updates),
            "sort_order": sort
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching sensor history: {str(e)}")