# routers/AlertScreen.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.firebase import get_sensor_data, get_all_tokens, send_notification, get_firestore_tokens
from typing import Optional
import os

router = APIRouter()

class AlertRequest(BaseModel):
    sensor_id: str
    force: bool = False


@router.get("/notification/tokens/debug", tags=["Notifications"])
async def debug_tokens():
    """
    Debug endpoint to check Firestore tokens (DEVELOPMENT ONLY)
    
    ⚠️ WARNING: This endpoint is disabled in production for security
    """
    # Check if we're in production
    if os.getenv("PRODUCTION", "false").lower() == "true":
        raise HTTPException(
            status_code=403, 
            detail="Debug endpoint disabled in production for security reasons"
        )
    
    try:
        from services.firebase import get_firestore_tokens
        
        tokens = get_firestore_tokens()
        
        return {
            "success": True,
            "tokens_found": len(tokens),
            # ⚠️ SECURITY: Never expose actual tokens in production!
            "tokens": ["***HIDDEN***"] * len(tokens),  # Masked tokens
            "message": f"Found {len(tokens)} FCM token(s) in Firestore 'devices' collection",
            "note": "Token values hidden for security (local development only)"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/notification/alerts", tags=["Notifications"])
async def send_alert_notification(req: AlertRequest):
    """
    Send alert notification for a sensor
    
    Gets FCM tokens from Firestore 'devices' collection and sends notification
    """
    try:
        sensor_id = req.sensor_id
        
        # Get latest sensor data
        sensor_data = get_sensor_data(sensor_id)
        
        # Handle case where sensor_data might be a list
        if isinstance(sensor_data, list):
            # If it's a list, get the first item (latest)
            sensor_data = sensor_data[0] if sensor_data else None
        
        # Check if sensor exists
        if not sensor_data and not req.force:
            raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
        
        # Get FCM tokens from Firestore devices collection
        tokens = get_all_tokens(sensor_id=sensor_id)
        
        if not tokens:
            return {
                "success": False,
                "error": "No FCM tokens found in Firestore",
                "sensor_id": sensor_id,
                "message": "Check Firestore 'devices' collection for fcmToken fields"
            }
        
        # Prepare notification data
        alert_data = {
            "title": f"🚨 Alert - Sensor {sensor_id}",
            "body": f"Suspicious activity detected at sensor {sensor_id}",
            "data": {
                "sensor_id": sensor_id,
                "type": "manual_alert",
                "timestamp": sensor_data.get("timestamp") if sensor_data else None
            }
        }
        
        # Send notification
        print(f"📤 Sending notification to {len(tokens)} device(s)...")
        result = send_notification(tokens, alert_data)
        
        return {
            "success": True,
            "sensor_id": sensor_id,
            "tokens_found": len(tokens),
            "notification_result": result,
            "message": f"Notification sent to {len(tokens)} device(s)"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error sending notification: {str(e)}")