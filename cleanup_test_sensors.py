# cleanup_test_sensors.py
"""Delete test sensors from Firebase"""

import os
from dotenv import load_dotenv
from firebase_admin import credentials, db, initialize_app
import json
import base64

load_dotenv()

def initialize_firebase():
    """Initialize Firebase"""
    try:
        from firebase_admin import get_app
        try:
            get_app()
            return
        except ValueError:
            pass
        
        base64_creds = os.getenv("FIREBASE_SERVICE_ACCOUNT_BASE64")
        if base64_creds:
            creds_json = base64.b64decode(base64_creds).decode('utf-8')
            creds_dict = json.loads(creds_json)
            cred = credentials.Certificate(creds_dict)
        else:
            cred = credentials.Certificate("firebase-service-account.json")
        
        db_url = os.getenv("FIREBASE_DATABASE_URL")
        initialize_app(cred, {'databaseURL': db_url})
        print("✅ Firebase initialized")
    except Exception as e:
        print(f"❌ Error: {e}")
        raise

def delete_test_sensors():
    """Delete test sensors"""
    test_sensors = [
        'SNR-2'
    ]
    
    print("\n🗑️  DELETING TEST SENSORS")
    print("="*60)
    
    for sensor_id in test_sensors:
        try:
            # Delete from sensors
            sensor_ref = db.reference(f'EcoWatch/sensors/{sensor_id}')
            if sensor_ref.get():
                sensor_ref.delete()
                print(f"   ✅ Deleted sensor: {sensor_id}")
            else:
                print(f"   ⏭️  Not found: {sensor_id}")
            
            # Delete predictions if they exist
            pred_ref = db.reference(f'EcoWatch/predictions/{sensor_id}')
            if pred_ref.get():
                pred_ref.delete()
                print(f"      ✅ Deleted predictions for {sensor_id}")
        
        except Exception as e:
            print(f"   ❌ Error deleting {sensor_id}: {e}")
    
    print("\n✅ Cleanup complete!")

if __name__ == "__main__":
    initialize_firebase()
    
    response = input("⚠️  Delete test sensors? (yes/no): ")
    if response.lower() == "yes":
        delete_test_sensors()
    else:
        print("❌ Cancelled")