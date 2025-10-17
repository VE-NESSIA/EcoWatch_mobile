# HomeScreen.py
from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List, Optional
from model import Sensor_data
from firebase_admin import db
from datetime import datetime

router = APIRouter()

def _parse_timestamp(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            pass
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts)
        except Exception:
            pass
    return datetime.min

def _last_update_from_updates_node(updates: Any) -> Optional[Dict[str, Any]]:
    """
    Given a node that may be a single update (dict) or a dict of push-keys -> update dicts,
    return the latest update (by timestamp) as a dict, or the single update.
    """
    if updates is None:
        return None
    if isinstance(updates, dict) and any(isinstance(v, dict) for v in updates.values()):
        entries = list(updates.values())
        entries.sort(key=lambda x: _parse_timestamp(x.get("timestamp")), reverse=True)
        return entries[0] if entries else None
    if isinstance(updates, dict):
        return updates
    return None

#sensor_id in URL path instead of JSON body
@router.post("/EcoWatch/sensors/{sensor_id}", response_model=Sensor_data)
async def create_sensorData(sensor_id: str, sensor_data: Sensor_data):
    try:
        sensors_ref = db.reference("EcoWatch/sensors")
        sensor_ref = sensors_ref.child(sensor_id)
        
        # Get existing data
        existing_data = sensor_ref.get() or []
        
        # Add new reading to array
        new_reading = {
            "sensor_id": sensor_id,
            "timestamp": sensor_data.timestamp.isoformat(),
            "activity": sensor_data.activity,
            "battery": sensor_data.battery,
            "signal_strength": sensor_data.signal_strength,
            "status": sensor_data.status,
            "isActive": sensor_data.isActive,
            "isTriggered": sensor_data.isTriggered
        }
        
        if isinstance(existing_data, list):
            existing_data.append(new_reading)
        else:
            # Convert to array if it's not already
            existing_data = [new_reading]
            
        sensor_ref.set(existing_data)
        return sensor_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#Add endpoint to get specific sensor data
@router.get("/EcoWatch/sensors/{sensor_id}")
async def get_sensor_data(sensor_id: str):
    """
    Get all data for a specific sensor_id.
    """
    try:
        sensors_ref = db.reference("EcoWatch/sensors")
        sensor_data = sensors_ref.child(sensor_id).get()
        
        if not sensor_data:
            raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
            
        # Normalize the data structure
        updates = _normalize_updates_node(sensor_data)
        return {
            "sensor_id": sensor_id,
            "readings": updates,
            "total_readings": len(updates)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/EcoWatch/sensors/{sensor_id}/latest")
async def get_latest_sensor_data(sensor_id: str):
    """
    Get the MOST RECENT data for a specific sensor_id.
    Returns only the latest reading.
    """
    try:
        sensors_ref = db.reference("EcoWatch/sensors")
        sensor_data = sensors_ref.child(sensor_id).get()
        
        if not sensor_data:
            raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
            
        # Get the latest reading from all available data
        latest_reading = _get_latest_reading(sensor_data)
        
        if not latest_reading:
            raise HTTPException(status_code=404, detail=f"No valid readings found for sensor {sensor_id}")
            
        return {
            "sensor_id": sensor_id,
            "latest_reading": latest_reading,
            "timestamp": latest_reading.get("timestamp")
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _get_latest_reading(sensor_data: Any) -> Optional[Dict[str, Any]]:
    """
    Extract the most recent reading from sensor data.
    Handles multiple data structures.
    """
    if sensor_data is None:
        return None
        
    # Case 1: Single reading (direct data)
    if isinstance(sensor_data, dict) and "sensor_id" in sensor_data:
        return sensor_data
        
    # Case 2: Multiple readings with Firebase push keys
    if isinstance(sensor_data, dict):
        readings = list(sensor_data.values())
        # Find the one with latest timestamp
        valid_readings = []
        for reading in readings:
            if isinstance(reading, dict) and reading.get("timestamp"):
                valid_readings.append(reading)
        
        if valid_readings:
            # Sort by timestamp descending and return the latest
            valid_readings.sort(key=lambda x: _parse_timestamp(x.get("timestamp")), reverse=True)
            return valid_readings[0]
    
    # Case 3: Array of readings
    if isinstance(sensor_data, list):
        valid_readings = [r for r in sensor_data if isinstance(r, dict) and r.get("timestamp")]
        if valid_readings:
            valid_readings.sort(key=lambda x: _parse_timestamp(x.get("timestamp")), reverse=True)
            return valid_readings[0]
            
    return None


# Helper function to normalize data
def _normalize_updates_node(updates: Any) -> List[Dict[str, Any]]:
    """
    Normalize Firebase node into list of update dicts.
    """
    if updates is None:
        return []
    if isinstance(updates, list):
        return updates
    if isinstance(updates, dict):
        if any(isinstance(v, dict) for v in updates.values()):
            return list(updates.values())
        return [updates]
    return []
