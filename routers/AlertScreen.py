# # routers/AlertScreen.py
# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel
# from services.firebase import get_sensor_data, get_all_tokens, send_notification, get_firestore_tokens
# from typing import Optional
# import os

# router = APIRouter()

# class AlertRequest(BaseModel):
#     sensor_id: str
#     force: bool = False


# @router.get("/notification/tokens/debug", tags=["Notifications"])
# async def debug_tokens():
#     """
#     Debug endpoint to check Firestore tokens (DEVELOPMENT ONLY)
    
#     ⚠️ WARNING: This endpoint is disabled in production for security
#     """
#     # Check if we're in production
#     if os.getenv("PRODUCTION", "false").lower() == "true":
#         raise HTTPException(
#             status_code=403, 
#             detail="Debug endpoint disabled in production for security reasons"
#         )
    
#     try:
#         from services.firebase import get_firestore_tokens
        
#         tokens = get_firestore_tokens()
        
#         return {
#             "success": True,
#             "tokens_found": len(tokens),
#             # ⚠️ SECURITY: Never expose actual tokens in production!
#             "tokens": ["***HIDDEN***"] * len(tokens),  # Masked tokens
#             "message": f"Found {len(tokens)} FCM token(s) in Firestore 'devices' collection",
#             "note": "Token values hidden for security (local development only)"
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# @router.post("/notification/alerts", tags=["Notifications"])
# async def send_alert_notification(req: AlertRequest):
#     """
#     Send alert notification for a sensor
    
#     Gets FCM tokens from Firestore 'devices' collection and sends notification
#     """
#     try:
#         sensor_id = req.sensor_id
        
#         # Get latest sensor data
#         sensor_data = get_sensor_data(sensor_id)
        
#         # Handle case where sensor_data might be a list
#         if isinstance(sensor_data, list):
#             # If it's a list, get the first item (latest)
#             sensor_data = sensor_data[0] if sensor_data else None
        
#         # Check if sensor exists
#         if not sensor_data and not req.force:
#             raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
        
#         # Get FCM tokens from Firestore devices collection
#         tokens = get_all_tokens(sensor_id=sensor_id)
        
#         if not tokens:
#             return {
#                 "success": False,
#                 "error": "No FCM tokens found in Firestore",
#                 "sensor_id": sensor_id,
#                 "message": "Check Firestore 'devices' collection for fcmToken fields"
#             }
        
#         # Prepare notification data
#         alert_data = {
#             "title": f"🚨 Alert - Sensor {sensor_id}",
#             "body": f"Suspicious activity detected at sensor {sensor_id}",
#             "data": {
#                 "sensor_id": sensor_id,
#                 "type": "manual_alert",
#                 "timestamp": sensor_data.get("timestamp") if sensor_data else None
#             }
#         }
        
#         # Send notification
#         print(f"📤 Sending notification to {len(tokens)} device(s)...")
#         result = send_notification(tokens, alert_data)
        
#         return {
#             "success": True,
#             "sensor_id": sensor_id,
#             "tokens_found": len(tokens),
#             "notification_result": result,
#             "message": f"Notification sent to {len(tokens)} device(s)"
#         }
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         raise HTTPException(status_code=500, detail=f"Error sending notification: {str(e)}")

# routers/AlertScreen.py
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from services.firebase import get_sensor_data, get_all_tokens, send_notification, get_firestore_tokens
from typing import Optional, List
from datetime import datetime
from firebase_admin import firestore
import os

router = APIRouter()

class AlertRequest(BaseModel):
    sensor_id: str
    force: bool = False

@router.get("/notification/alerts", tags=["Notifications"])
async def get_alerts(
    sensor_id: Optional[str] = Query(None, description="Filter by sensor ID"),
    limit: Optional[int] = Query(50, ge=1, le=500, description="Maximum number of alerts to return")
):
    """
    Get notification/alert history from Firestore
    
    **Parameters:**
    - `sensor_id`: Optional - Filter alerts by specific sensor
    - `limit`: Maximum number of alerts to return (default: 50, max: 500)
    
    **Returns:**
    - List of alerts with details and metadata
    
    **Example:**
    - `/notification/alerts` - Get all recent alerts
    - `/notification/alerts?sensor_id=SENSOR_001` - Get alerts for specific sensor
    - `/notification/alerts?limit=10` - Get last 10 alerts
    """
    try:
        db = firestore.client()
        
        # Try multiple collection names
        collection_names = ['alerts', 'notifications', 'alert_history']
        
        for collection_name in collection_names:
            try:
                alerts_ref = db.collection(collection_name)
                
                # Build query based on parameters
                if sensor_id:
                    # Use filter parameter (new syntax) instead of where
                    query = alerts_ref.where(filter=firestore.FieldFilter('sensor_id', '==', sensor_id))
                else:
                    query = alerts_ref
                
                # Try to order by timestamp if available
                try:
                    query = query.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
                except Exception:
                    # If ordering fails (no index or field), just limit
                    query = query.limit(limit)
                
                # Execute query
                docs = list(query.stream())
                
                if docs:  # If we found documents, use this collection
                    alerts = []
                    for doc in docs:
                        alert_data = doc.to_dict()
                        alert_data['id'] = doc.id
                        alerts.append(alert_data)
                    
                    # Sort in Python if Firestore ordering failed
                    if 'timestamp' in alerts[0]:
                        alerts.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
                    
                    return {
                        "success": True,
                        "alerts": alerts,
                        "count": len(alerts),
                        "collection": collection_name,
                        "filter": {
                            "sensor_id": sensor_id,
                            "limit": limit
                        }
                    }
            except Exception as e:
                print(f"Failed to query collection '{collection_name}': {str(e)}")
                continue
        
        # If no collection had data, return empty result
        return {
            "success": True,
            "alerts": [],
            "count": 0,
            "filter": {
                "sensor_id": sensor_id,
                "limit": limit
            },
            "message": f"No alerts found. Checked collections: {', '.join(collection_names)}",
            "note": "Alerts will appear here after sending notifications via POST /notification/alerts"
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail=f"Error fetching alerts: {str(e)}"
        )

@router.get("/notification/alerts/collections", tags=["Notifications"])
async def list_alert_collections():
    """
    List available Firestore collections and their document counts
    
    Useful for debugging - shows what collections exist in your Firestore
    """
    try:
        db = firestore.client()
        
        # Collections to check
        check_collections = ['alerts', 'notifications', 'alert_history', 'devices']
        
        results = {}
        for coll_name in check_collections:
            try:
                docs = list(db.collection(coll_name).limit(1).stream())
                count_estimate = len(list(db.collection(coll_name).limit(100).stream()))
                
                results[coll_name] = {
                    "exists": len(docs) > 0,
                    "document_count_estimate": count_estimate if count_estimate < 100 else "100+",
                    "sample_doc_id": docs[0].id if docs else None
                }
            except Exception as e:
                results[coll_name] = {
                    "exists": False,
                    "error": str(e)
                }
        
        return {
            "success": True,
            "collections": results,
            "note": "Use POST /notification/alerts to create alert records"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

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
   
    Gets FCM tokens from Firestore 'devices' collection and sends notification.
    Also logs the alert to Firestore for history tracking.
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
        
        # Log alert to Firestore for history
        try:
            db = firestore.client()
            alert_record = {
                "sensor_id": sensor_id,
                "title": alert_data["title"],
                "body": alert_data["body"],
                "type": "manual_alert",
                "timestamp": firestore.SERVER_TIMESTAMP,
                "tokens_sent": len(tokens),
                "notification_result": result,
                "sensor_data": sensor_data
            }
            
            # Try to save to 'alerts' collection
            db.collection('alerts').add(alert_record)
            
        except Exception as log_error:
            print(f"⚠️ Warning: Could not log alert to Firestore: {str(log_error)}")
            # Don't fail the whole request if logging fails
       
        return {
            "success": True,
            "sensor_id": sensor_id,
            "tokens_found": len(tokens),
            "notification_result": result,
            "message": f"Notification sent to {len(tokens)} device(s)",
            "alert_logged": True
        }
       
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error sending notification: {str(e)}")