# services/firebase.py
import os
import json
import base64
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db, messaging, firestore

load_dotenv()

try:
    from model import Sensor_data
except Exception:
    Sensor_data = None  # used only for typing if available

# ============================================================================
# FIREBASE INITIALIZATION - Supports both Local and Railway Deployment
# ============================================================================

def initialize_firebase():
    """
    Initialize Firebase with support for both local and Railway environments
    - Local: Uses firebase-service-account.json file
    - Railway: Uses base64-encoded credentials from environment variable
    """
    try:
        # Check if already initialized
        try:
            firebase_admin.get_app()
            print("✅ Firebase already initialized")
            return
        except ValueError:
            pass  # Not initialized yet, proceed
        
        # Get database URL
        DATABASE_URL = os.environ.get("FIREBASE_DATABASE_URL")
        if not DATABASE_URL:
            raise ValueError(
                "FIREBASE_DATABASE_URL environment variable is required. "
                "Please set it in your .env file or environment variables. "
                "It should look like: https://your-project-id-default-rtdb.firebaseio.com/"
            )
        
        # Check if running on Railway (production)
        if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_STATIC_URL"):
            print("🚂 Railway environment detected, using base64 credentials...")
            
            # Get base64-encoded service account
            base64_creds = os.getenv("FIREBASE_SERVICE_ACCOUNT_BASE64")
            if not base64_creds:
                raise ValueError(
                    "FIREBASE_SERVICE_ACCOUNT_BASE64 not found in Railway environment. "
                    "Please add it to your Railway environment variables."
                )
            
            try:
                # Decode base64 to JSON
                json_creds = base64.b64decode(base64_creds).decode('utf-8')
                service_account_info = json.loads(json_creds)
                
                # Initialize with decoded credentials
                cred = credentials.Certificate(service_account_info)
                print("✅ Firebase credentials decoded from base64")
            except Exception as e:
                raise ValueError(f"Failed to decode base64 credentials: {e}")
        
        else:
            # Local development - use JSON file
            print("💻 Local environment detected, using JSON file...")
            
            SERVICE_ACCOUNT_PATH = os.environ.get(
                "GOOGLE_APPLICATION_CREDENTIALS",
                "firebase-service-account.json"
            )
            
            if not os.path.exists(SERVICE_ACCOUNT_PATH):
                raise RuntimeError(
                    f"Firebase service account file not found: {SERVICE_ACCOUNT_PATH}\n"
                    f"Please ensure the file exists or set GOOGLE_APPLICATION_CREDENTIALS"
                )
            
            # Validate JSON
            try:
                with open(SERVICE_ACCOUNT_PATH, 'r') as f:
                    json.load(f)  # Test if valid JSON
            except Exception as e:
                raise RuntimeError(f"Invalid service account JSON: {e}")
            
            # Initialize with file
            cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
            print(f"✅ Firebase credentials loaded from {SERVICE_ACCOUNT_PATH}")
        
        # Initialize Firebase app
        firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
        print("✅ Firebase initialized successfully")
        
        # Test database connection
        ref = db.reference("/")
        ref.get()
        print("✅ Database connection test passed")
        
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        raise

# Initialize Firebase on module import
initialize_firebase()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

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


def _sort_entries_by_timestamp(entries: list, newest_first: bool = True) -> list:
    return sorted(entries, key=lambda x: _parse_timestamp(x.get("timestamp")), reverse=newest_first)

def create_sensor_data(sensor) -> Dict[str, Any]:
    """
    Push a new sensor data entry under EcoWatch/sensors.
    sensor may be a Pydantic model or a dict-like object.
    """
    try:
        ref = db.reference("EcoWatch/sensors")
        payload = {
            "sensor_id": getattr(sensor, "sensor_id", None) or sensor.get("sensor_id"),
            "timestamp": getattr(sensor, "timestamp", None) or sensor.get("timestamp"),
            "activity": getattr(sensor, "activity", None) or sensor.get("activity"),
            "battery": getattr(sensor, "battery", None) or sensor.get("battery"),
            "signal_strength": getattr(sensor, "signal_strength", None) or sensor.get("signal_strength"),
            "status": getattr(sensor, "status", None) or sensor.get("status"),
            "isActive": getattr(sensor, "isActive", None) or sensor.get("isActive"),
            "isTriggered": getattr(sensor, "isTriggered", None) or sensor.get("isTriggered", False),
        }
        new_ref = ref.push(payload)
        return {"id": new_ref.key, "message": "Sensor data stored successfully"}
    except Exception as e:
        return {"error": str(e)}


def get_sensor_data(sensor_id: str) -> Optional[Dict[str, Any]]:
    """
    Return the most recent sensor data for sensor_id.
    Looks under EcoWatch/sensors/<sensor_id> first; if that node has multiple entries,
    returns the newest by timestamp. Falls back to scanning children if needed.
    """
    try:
        ref = db.reference("EcoWatch/sensors")
        node = ref.child(sensor_id).get()
        if node:
            if isinstance(node, dict) and any(isinstance(v, dict) for v in node.values()):
                entries = list(node.values())
                sorted_entries = _sort_entries_by_timestamp(entries, newest_first=True)
                return sorted_entries[0] if sorted_entries else None
            return node

        # fallback: scan all sensors for matching sensor_id
        all_sensors = ref.get() or {}
        matches: List[Dict[str, Any]] = []
        for _, updates in all_sensors.items():
            if isinstance(updates, dict):
                if any(isinstance(v, dict) for v in updates.values()):
                    for v in updates.values():
                        if v and v.get("sensor_id") == sensor_id:
                            matches.append(v)
                else:
                    if updates.get("sensor_id") == sensor_id:
                        matches.append(updates)
        if not matches:
            return None
        matches = _sort_entries_by_timestamp(matches, newest_first=True)
        return matches[0]
    except Exception:
        return None


def get_firebase_tokens(sensor_id: str) -> List[str]:
    """
    Return a deduplicated list of FCM tokens related to a sensor_id.
    Checks common locations under the DB and returns [] on error.
    """
    try:
        candidates: List[str] = []
        paths = [
            f"EcoWatch/tokens/{sensor_id}",
            f"tokens/{sensor_id}",
            f"EcoWatch/sensors/{sensor_id}/tokens",
            f"EcoWatch/sensors/{sensor_id}/push_tokens",
            f"sensors/{sensor_id}/tokens",
            f"users/{sensor_id}/tokens",
        ]
        for p in paths:
            node = db.reference(p).get()
            if not node:
                continue
            if isinstance(node, list):
                candidates.extend([t for t in node if isinstance(t, str)])
            elif isinstance(node, dict):
                for v in node.values():
                    if isinstance(v, str):
                        candidates.append(v)
                    elif isinstance(v, dict):
                        if "token" in v and isinstance(v["token"], str):
                            candidates.append(v["token"])
                        else:
                            for sub in v.values():
                                if isinstance(sub, str):
                                    candidates.append(sub)
            elif isinstance(node, str):
                candidates.append(node)

        # deduplicate while preserving order
        seen = set()
        tokens: List[str] = []
        for t in candidates:
            if t and t not in seen:
                seen.add(t)
                tokens.append(t)
        return tokens
    except Exception:
        return []

def get_firestore_tokens(sensor_id: str = None, user_id: str = None) -> List[str]:
    """
    Get FCM tokens from Firestore 'devices' collection
    
    Args:
        sensor_id: Optional sensor ID (not used currently, for future filtering)
        user_id: Optional user ID (not used currently, for future filtering)
    
    Returns:
        List of FCM tokens from all devices
    """
    try:
        db_firestore = firestore.client()
        tokens = []
        
        # Query the 'devices' collection
        devices_ref = db_firestore.collection('devices')
        
        # Get all device documents
        docs = devices_ref.stream()
        
        # Extract fcmToken from each device
        for doc in docs:
            data = doc.to_dict()
            
            # Check for fcmToken field
            if 'fcmToken' in data and data['fcmToken']:
                tokens.append(data['fcmToken'])
            # Also check alternative field names (just in case)
            elif 'fcm_token' in data and data['fcm_token']:
                tokens.append(data['fcm_token'])
            elif 'token' in data and data['token']:
                tokens.append(data['token'])
        
        # Deduplicate tokens
        unique_tokens = list(set(tokens))
        
        print(f"📱 Found {len(unique_tokens)} FCM token(s) in Firestore devices collection")
        
        return unique_tokens
        
    except Exception as e:
        print(f"❌ Error getting Firestore tokens: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_all_tokens(sensor_id: str = None, user_id: str = None) -> List[str]:
    """
    Get FCM tokens from BOTH Realtime Database AND Firestore
    
    Args:
        sensor_id: Optional sensor ID
        user_id: Optional user ID
    
    Returns:
        Combined deduplicated list of tokens
    """
    tokens = []
    
    # Get from Realtime Database (if sensor_id provided)
    if sensor_id:
        realtime_tokens = get_firebase_tokens(sensor_id)
        tokens.extend(realtime_tokens)
        if realtime_tokens:
            print(f"📊 Found {len(realtime_tokens)} token(s) in Realtime Database")
    
    # Get from Firestore 'devices' collection (gets all devices)
    firestore_tokens = get_firestore_tokens(sensor_id=sensor_id, user_id=user_id)
    tokens.extend(firestore_tokens)
    
    # Deduplicate and return
    unique_tokens = list(set(tokens))
    print(f"📤 Total unique tokens: {len(unique_tokens)}")
    
    return unique_tokens



def get_first_update_each_sensor() -> Dict[str, Any]:
    """
    Returns the earliest update for each sensor (keeps for compatibility).
    """
    try:
        ref = db.reference("EcoWatch/sensors")
        all_sensors = ref.get() or {}
        first_updates: Dict[str, Any] = {}
        for sensor_id, updates in all_sensors.items():
            if isinstance(updates, dict) and any(isinstance(v, dict) for v in updates.values()):
                entries = list(updates.values())
                sorted_entries = _sort_entries_by_timestamp(entries, newest_first=False)
                first_updates[sensor_id] = sorted_entries[0] if sorted_entries else None
            else:
                first_updates[sensor_id] = updates
        return first_updates
    except Exception as e:
        return {"error": str(e)}


def send_notification(tokens: List[str], alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send multicast notification via FCM with improved error handling.
    Handles large token lists by batching (max 500 per batch).
    Returns a dict with detailed results.
    """
    try:
        if not tokens:
            return {"error": "no tokens provided", "success_count": 0, "failure_count": 0}
        
        # Filter out any empty or invalid tokens
        valid_tokens = [t for t in tokens if t and isinstance(t, str) and len(t) > 10]
        
        if not valid_tokens:
            return {"error": "no valid tokens provided", "success_count": 0, "failure_count": 0}
        
        print(f"📤 Preparing to send to {len(valid_tokens)} valid token(s)")
        
        total_success = 0
        total_failure = 0
        failed_tokens = []
        
        # FCM allows max 500 tokens per multicast, batch if needed
        BATCH_SIZE = 500
        
        for i in range(0, len(valid_tokens), BATCH_SIZE):
            batch_tokens = valid_tokens[i:i + BATCH_SIZE]
            
            try:
                # Build message
                message = messaging.MulticastMessage(
                    tokens=batch_tokens,
                    notification=messaging.Notification(
                        title=alert_data.get("title", "Alert"),
                        body=alert_data.get("body", "New Notification"),
                    ),
                    data={k: str(v) for k, v in alert_data.get("data", {}).items()},  # Ensure all data values are strings
                    android=messaging.AndroidConfig(
                        priority='high',
                        notification=messaging.AndroidNotification(
                            sound='default',
                            channel_id='alerts'
                        )
                    ),
                    apns=messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                sound='default',
                                badge=1
                            )
                        )
                    )
                )
                
                # Send multicast
                response = messaging.send_multicast(message)
                
                total_success += response.success_count
                total_failure += response.failure_count
                
                # Log individual failures for debugging
                if response.failure_count > 0:
                    for idx, resp in enumerate(response.responses):
                        if not resp.success:
                            token = batch_tokens[idx]
                            error_msg = str(resp.exception) if resp.exception else "Unknown error"
                            failed_tokens.append({"token": token[:20] + "...", "error": error_msg})
                            print(f"   ❌ Failed to send to token {idx + 1}: {error_msg}")
                
                print(f"   ✅ Batch {i//BATCH_SIZE + 1}: {response.success_count} success, {response.failure_count} failed")
                
            except Exception as batch_error:
                print(f"   ❌ Batch {i//BATCH_SIZE + 1} failed: {str(batch_error)}")
                total_failure += len(batch_tokens)
                failed_tokens.append({"batch": i//BATCH_SIZE + 1, "error": str(batch_error)})
        
        result = {
            "success_count": total_success,
            "failure_count": total_failure,
            "total_tokens": len(valid_tokens)
        }
        
        if failed_tokens:
            result["failed_tokens"] = failed_tokens[:5]  # Only return first 5 to avoid huge responses
        
        return result
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"❌ send_notification error: {error_detail}")
        return {
            "error": str(e),
            "success_count": 0,
            "failure_count": len(tokens) if tokens else 0,
            "details": error_detail
        }
        
def _normalize_updates_node(updates: Any) -> List[Dict[str, Any]]:
    """
    Normalize a Firebase node into a list of update dicts.
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


def get_all_sensors_history(limit: Optional[int] = None, newest_first: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return full history for all sensors under EcoWatch/sensors.
    - limit: optional per-sensor max number of updates to return
    - newest_first: True for newest-first (desc), False for oldest-first (asc)
    """
    try:
        ref = db.reference("EcoWatch/sensors")
        all_sensors = ref.get() or {}
        result: Dict[str, List[Dict[str, Any]]] = {}

        for sensor_id, node in all_sensors.items():
            updates = _normalize_updates_node(node)
            sorted_updates = _sort_entries_by_timestamp(updates, newest_first=newest_first)
            if limit is not None:
                sorted_updates = sorted_updates[:limit]
            result[sensor_id] = sorted_updates

        return result
    except Exception:
        return {}


def get_sensor_history(sensor_id: str, limit: Optional[int] = None, newest_first: bool = True) -> Optional[List[Dict[str, Any]]]:
    """
    Return full history for a single sensor_id.
    Returns a list of update dicts (possibly empty) or None on error/not found.
    """
    try:
        ref = db.reference("EcoWatch/sensors")
        node = ref.child(sensor_id).get()
        if node is None:
            return []
        updates = _normalize_updates_node(node)
        sorted_updates = _sort_entries_by_timestamp(updates, newest_first=newest_first)
        if limit is not None:
            sorted_updates = sorted_updates[:limit]
        return sorted_updates
    except Exception:
        return None


def _normalize_node_to_latest(node: Any) -> Optional[Dict[str, Any]]:
    """
    Given a DB node for a sensor, return the latest update dict or the single update.
    Compatible with:
    - push-key -> update dicts
    - single update dict
    - None -> None
    """
    if node is None:
        return None
    if isinstance(node, dict):
        # push-keys -> dicts
        if any(isinstance(v, dict) for v in node.values()):
            entries = [v for v in node.values() if isinstance(v, dict)]
            entries.sort(key=lambda e: _parse_timestamp(e.get("timestamp")), reverse=True)
            return entries[0] if entries else None
        return node
    return None


def get_network_summary() -> Dict[str, Any]:
    """
    Returns network summary used by InfoScreen.router:
    {
    total_sensors, online_count, offline_count, offline_sensor_ids,
    average_signal_strength, area_info, maintenance
    }
    """
    try:
        ref = db.reference("EcoWatch/sensors")
        all_sensors = ref.get() or {}
    except Exception as e:
        return {"error": f"DB error: {e}"}

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
            try:
                s = float(latest.get("signal_strength"))
                online = s > -1000
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

# export for routers
_existing = list(globals().get("__all__", []))
_existing.extend(["get_network_summary", "_normalize_node_to_latest", "_parse_timestamp"])
__all__ = _existing
