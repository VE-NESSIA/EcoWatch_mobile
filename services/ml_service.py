# services/ml_service.py
from typing import Dict, Any, Optional, List
from ml_models.predictor import get_predictor
from services.firebase import send_notification, get_firebase_tokens
from firebase_admin import db
from datetime import datetime

def predict_and_store(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run ML prediction and store results in Firebase
    
    Args:
        sensor_data: Sensor reading data
    
    Returns:
        Prediction results
    """
    try:
        predictor = get_predictor()
        
        # Make prediction
        prediction_result = predictor.predict(sensor_data)
        
        # Store prediction in Firebase
        sensor_id = sensor_data.get("sensor_id")
        if sensor_id:
            predictions_ref = db.reference(f"EcoWatch/predictions/{sensor_id}")
            predictions_ref.push({
                **prediction_result,
                "sensor_data": sensor_data,
                "created_at": datetime.utcnow().isoformat()
            })
        
        return prediction_result
        
    except Exception as e:
        return {
            "error": str(e),
            "is_alert": False,
            "timestamp": datetime.utcnow().isoformat()
        }


def predict_and_alert(sensor_data: Dict[str, Any], auto_notify: bool = True) -> Dict[str, Any]:
    """
    Run prediction and automatically send alert if illegal activity detected
    
    Args:
        sensor_data: Sensor reading data
        auto_notify: Whether to automatically send notifications
    
    Returns:
        Combined prediction and notification results
    """
    # Get prediction
    prediction_result = predict_and_store(sensor_data)
    
    # Send alert if needed
    notification_result = None
    if prediction_result.get("is_alert") and auto_notify:
        sensor_id = sensor_data.get("sensor_id")
        confidence = prediction_result.get("confidence", 0)
        alert_level = prediction_result.get("alert_level", "medium")
        
        # Prepare alert data
        alert_emoji = "🚨" if alert_level == "high" else "⚠️"
        alert_data = {
            "title": f"{alert_emoji} Mining Alert - Sensor {sensor_id}",
            "body": f"{prediction_result['class_label']} detected with {confidence:.1%} confidence",
            "data": {
                "sensor_id": sensor_id,
                "prediction": str(prediction_result['prediction']),
                "class_label": prediction_result['class_label'],
                "confidence": str(confidence),
                "alert_level": alert_level,
                "timestamp": prediction_result['timestamp'],
                "type": "mining_detection"
            }
        }
        
        # Get tokens and send notification
        tokens = get_firebase_tokens(sensor_id)
        if tokens:
            notification_result = send_notification(tokens, alert_data)
        else:
            notification_result = {"error": "No FCM tokens found for sensor"}
    
    return {
        "prediction": prediction_result,
        "notification": notification_result,
        "alert_sent": notification_result is not None and notification_result.get("success_count", 0) > 0
    }


def batch_predict(sensor_ids: List[str], auto_notify: bool = False) -> Dict[str, Any]:
    """
    Run predictions on multiple sensors
    
    Args:
        sensor_ids: List of sensor IDs to predict
        auto_notify: Whether to send notifications
    
    Returns:
        Batch prediction results
    """
    from services.firebase import get_sensor_data
    
    results = []
    for sensor_id in sensor_ids:
        try:
            sensor_data = get_sensor_data(sensor_id)
            if sensor_data:
                result = predict_and_alert(sensor_data, auto_notify=auto_notify)
                results.append({
                    "sensor_id": sensor_id,
                    "success": True,
                    **result
                })
            else:
                results.append({
                    "sensor_id": sensor_id,
                    "success": False,
                    "error": "Sensor not found"
                })
        except Exception as e:
            results.append({
                "sensor_id": sensor_id,
                "success": False,
                "error": str(e)
            })
    
    return {
        "total": len(sensor_ids),
        "successful": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "results": results
    }