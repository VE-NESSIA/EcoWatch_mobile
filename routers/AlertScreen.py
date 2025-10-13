from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.firebase import get_sensor_data, get_firebase_tokens, send_notification

router = APIRouter()

class AlertRequest(BaseModel):
    sensor_id: str
    force: bool = False  # set true to force sending regardless of conditions

@router.post('/notification/alerts')
async def send_alerts(req: AlertRequest):
    # fetch latest sensor data
    sensor_data = get_sensor_data(req.sensor_id)
    if not sensor_data:
        raise HTTPException(status_code=404, detail="Sensor not found")

    # determine alert conditions (customize thresholds/logic as needed)
    battery = sensor_data.get("battery")
    activity = sensor_data.get("activity")
    is_triggered = bool(sensor_data.get("isTriggered") or sensor_data.get("is_triggered"))

    low_battery = isinstance(battery, (int, float)) and battery < 20
    activity_detected = bool(activity and str(activity).strip().lower() not in ("idle", "none", ""))

    if not (req.force or is_triggered or low_battery or activity_detected):
        return {"sent": False, "reason": "No alert conditions met"}

    # build notification payload
    reason = "Triggered" if is_triggered else "Activity detected" if activity_detected else "Battery low"
    alert_data = {
        "title": f"Alert for Sensor {req.sensor_id}",
        "body": f"{reason} on sensor {req.sensor_id}",
        "data": {"sensor_id": req.sensor_id, "reason": reason}
    }

    # get user tokens and send
    tokens = get_firebase_tokens(req.sensor_id)
    if not tokens:
        raise HTTPException(status_code=404, detail="No valid tokens found")

    result = send_notification(tokens, alert_data)
    return {"sent": True, "result": result}