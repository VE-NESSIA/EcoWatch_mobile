# routers/HomeScreen.py - COMPLETE WITH AUTO-NOTIFICATIONS
from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List, Optional
from model import Sensor_data
from firebase_admin import db, firestore
from datetime import datetime
from services.ml_service import predict_and_alert
from services.firebase import get_all_tokens, send_notification

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

async def send_alert_if_mining_detected(sensor_id: str, sensor_data: Dict[str, Any], prediction_result: Dict[str, Any]):
    """
    Automatically send notification if mining is detected
    """
    try:
        # Extract prediction info
        prediction = prediction_result.get('prediction', {})
        is_alert = prediction.get('is_alert', False) or prediction.get('prediction') == 1
        confidence = prediction.get('confidence', 0)
        
        if not is_alert:
            return None  # Not an alert, skip
        
        print(f"🚨 ALERT DETECTED: Attempting to send notification for {sensor_id}")
        
        # Get FCM tokens
        tokens = get_all_tokens(sensor_id=sensor_id)
        
        if not tokens:
            print(f"⚠️ No FCM tokens found for {sensor_id}")
            return {
                "notification_sent": False,
                "reason": "no_tokens",
                "message": "No devices registered for notifications"
            }
        
        # Prepare notification
        alert_data = {
            "title": f"🚨 Mining Alert - {sensor_id}",
            "body": f"Possible illegal mining detected! Confidence: {confidence*100:.1f}%",
            "data": {
                "sensor_id": sensor_id,
                "type": "auto_alert",
                "confidence": str(confidence),
                "timestamp": sensor_data.get("timestamp"),
                "activity": sensor_data.get("activity")
            }
        }
        
        # Send notification
        result = send_notification(tokens, alert_data)
        print(f"✅ Notification sent to {len(tokens)} device(s)")
        
        # Log to Firestore
        try:
            firestore_db = firestore.client()
            alert_record = {
                "sensor_id": sensor_id,
                "title": alert_data["title"],
                "body": alert_data["body"],
                "type": "auto_alert",
                "timestamp": firestore.SERVER_TIMESTAMP,
                "confidence": confidence,
                "prediction": prediction.get('prediction', 0),
                "tokens_sent": len(tokens),
                "notification_result": result,
                "sensor_data": sensor_data,
                "ml_prediction": prediction_result
            }
            
            firestore_db.collection('alerts').add(alert_record)
            print(f"📝 Alert logged to Firestore 'alerts' collection")
            
        except Exception as log_error:
            print(f"⚠️ Failed to log alert to Firestore: {str(log_error)}")
        
        return {
            "notification_sent": True,
            "tokens_count": len(tokens),
            "notification_result": result
        }
        
    except Exception as e:
        print(f"❌ Error sending auto-notification: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "notification_sent": False,
            "error": str(e)
        }

#sensor_id in URL path instead of JSON body
@router.post("/EcoWatch/sensors/{sensor_id}", response_model=Sensor_data)
async def create_sensorData(sensor_id: str, sensor_data: Sensor_data):
    try:
        sensors_ref = db.reference("EcoWatch/sensors")
        sensor_ref = sensors_ref.child(sensor_id)
        
        # Get existing data
        existing_data = sensor_ref.get() or []
        
        # Build new reading with ALL fields including CSV features
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
        
        # ✅ CRITICAL: Add CSV feature values if present
        if sensor_data.Max_Amplitude is not None:
            new_reading["Max_Amplitude"] = sensor_data.Max_Amplitude
        if sensor_data.RMS_Ratio is not None:
            new_reading["RMS_Ratio"] = sensor_data.RMS_Ratio
        if sensor_data.Power_Ratio is not None:
            new_reading["Power_Ratio"] = sensor_data.Power_Ratio
        
        # Debug logging
        has_features = all([
            sensor_data.Max_Amplitude is not None,
            sensor_data.RMS_Ratio is not None,
            sensor_data.Power_Ratio is not None
        ])
        
        if has_features:
            print(f"✅ Received CSV features: Max={sensor_data.Max_Amplitude:.6f}, RMS={sensor_data.RMS_Ratio:.2f}, Power={sensor_data.Power_Ratio:.2f}")
        else:
            print(f"⚠️ Missing CSV features - ML prediction may be inaccurate")
        
        if isinstance(existing_data, list):
            existing_data.append(new_reading)
        else:
            existing_data = [new_reading]
            
        sensor_ref.set(existing_data)
        
        # 🆕 AUTO-PREDICTION & AUTO-NOTIFICATION
        prediction_result = None
        notification_result = None
        
        try:
            # Run ML prediction (don't let it send notification, we handle it ourselves)
            prediction_result = predict_and_alert(new_reading, auto_notify=False)
            
            prediction_class = prediction_result.get('prediction', {}).get('class_label', 'Unknown')
            print(f"✅ ML Prediction for {sensor_id}: {prediction_class}")
            
            # 🚨 AUTO-SEND NOTIFICATION IF MINING DETECTED
            notification_result = await send_alert_if_mining_detected(
                sensor_id,
                new_reading,
                prediction_result
            )
            
            if notification_result and notification_result.get('notification_sent'):
                token_count = notification_result.get('tokens_count', 0)
                print(f"   🚨 Auto-notification sent to {token_count} device(s)")
            elif notification_result and not notification_result.get('notification_sent'):
                reason = notification_result.get('reason', 'unknown')
                print(f"   ⚠️ Notification not sent: {reason}")
            
        except Exception as e:
            print(f"⚠️ ML Prediction/Notification failed for {sensor_id}: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail the whole request if prediction fails
        
        # Log results for debugging (since we can't modify response model)
        if prediction_result:
            print(f"📊 Full prediction result: {prediction_result}")
        if notification_result:
            print(f"📲 Notification result: {notification_result}")
        
        return sensor_data
        
    except Exception as e:
        import traceback
        traceback.print_exc()
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