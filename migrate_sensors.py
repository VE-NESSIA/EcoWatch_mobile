# migrate_sensors.py
"""
Migration script to check and normalize sensor IDs in Firebase Realtime Database

Run this script to:
1. Check all existing sensor IDs
2. Ensure they match the SNR-XXX format
3. Optionally rename/migrate old format sensors
"""

import os
from dotenv import load_dotenv
from firebase_admin import credentials, db, initialize_app
import json
import base64
import re

# Load environment variables
load_dotenv()

def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    try:
        # Check if already initialized
        from firebase_admin import get_app
        try:
            get_app()
            print("✅ Firebase already initialized")
            return
        except ValueError:
            pass
        
        # Get credentials
        base64_creds = os.getenv("FIREBASE_SERVICE_ACCOUNT_BASE64")
        if base64_creds:
            print("🔑 Using base64 credentials...")
            creds_json = base64.b64decode(base64_creds).decode('utf-8')
            creds_dict = json.loads(creds_json)
            cred = credentials.Certificate(creds_dict)
        else:
            print("🔑 Using service account file...")
            cred = credentials.Certificate("firebase-service-account.json")
        
        # Initialize
        db_url = os.getenv("FIREBASE_DATABASE_URL")
        initialize_app(cred, {'databaseURL': db_url})
        print("✅ Firebase initialized successfully")
        
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        raise


def get_all_sensor_ids():
    """Get all sensor IDs from Firebase"""
    try:
        ref = db.reference('EcoWatch/sensors')
        sensors = ref.get()
        
        if not sensors:
            print("⚠️  No sensors found in database")
            return []
        
        sensor_ids = list(sensors.keys())
        print(f"📊 Found {len(sensor_ids)} sensor(s) in database")
        return sensor_ids
        
    except Exception as e:
        print(f"❌ Error getting sensors: {e}")
        return []


def validate_sensor_id(sensor_id):
    """Check if sensor ID matches SNR-XXX format"""
    pattern = r'^SNR-\d{3,}$'
    return bool(re.match(pattern, sensor_id))


def normalize_sensor_id(sensor_id):
    """
    Normalize old sensor ID formats to SNR-XXX format
    
    Examples:
    - SENSOR_001 → SNR-001
    - SENSOR-001 → SNR-001
    - sensor_001 → SNR-001
    - TEST_001 → SNR-001
    - 001 → SNR-001
    """
    # If already valid, return as-is
    if validate_sensor_id(sensor_id):
        return sensor_id
    
    # Try to extract number
    numbers = re.findall(r'\d+', sensor_id)
    if numbers:
        # Get the last number found (usually the sensor number)
        number = numbers[-1]
        # Keep original length (dynamic padding)
        return f'SNR-{number}'
    
    # Can't normalize - return original
    return sensor_id


def migrate_sensors(dry_run=True):
    """
    Migrate sensors to new format
    
    Args:
        dry_run: If True, only show what would be changed without making changes
    """
    print("\n" + "="*60)
    print("🔄 SENSOR ID MIGRATION SCRIPT")
    print("="*60)
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    else:
        print("⚠️  LIVE MODE - Database will be modified!")
    
    print()
    
    # Get all sensors
    sensor_ids = get_all_sensor_ids()
    
    if not sensor_ids:
        print("✅ No sensors to migrate")
        return
    
    # Check each sensor
    valid_sensors = []
    invalid_sensors = []
    
    for sensor_id in sensor_ids:
        if validate_sensor_id(sensor_id):
            valid_sensors.append(sensor_id)
        else:
            invalid_sensors.append(sensor_id)
    
    # Report status
    print(f"\n📊 MIGRATION REPORT")
    print(f"   Total sensors: {len(sensor_ids)}")
    print(f"   ✅ Valid format (SNR-XXX): {len(valid_sensors)}")
    print(f"   ⚠️  Need migration: {len(invalid_sensors)}")
    
    if valid_sensors:
        print(f"\n✅ Valid Sensors ({len(valid_sensors)}):")
        for sid in valid_sensors[:10]:  # Show first 10
            print(f"   - {sid}")
        if len(valid_sensors) > 10:
            print(f"   ... and {len(valid_sensors) - 10} more")
    
    if invalid_sensors:
        print(f"\n⚠️  Sensors Needing Migration ({len(invalid_sensors)}):")
        migration_plan = []
        
        for old_id in invalid_sensors:
            new_id = normalize_sensor_id(old_id)
            migration_plan.append((old_id, new_id))
            
            if old_id != new_id:
                print(f"   - {old_id} → {new_id}")
            else:
                print(f"   - {old_id} → ❌ Cannot auto-migrate (manual fix needed)")
        
        # Perform migration if not dry run
        if not dry_run and migration_plan:
            print(f"\n🔄 Starting migration...")
            
            for old_id, new_id in migration_plan:
                if old_id == new_id:
                    print(f"   ⏭️  Skipping {old_id} (cannot auto-migrate)")
                    continue
                
                try:
                    # Get old data
                    old_ref = db.reference(f'EcoWatch/sensors/{old_id}')
                    data = old_ref.get()
                    
                    if data:
                        # Update sensor_id in data
                        if isinstance(data, dict):
                            data['sensor_id'] = new_id
                        
                        # Write to new location
                        new_ref = db.reference(f'EcoWatch/sensors/{new_id}')
                        new_ref.set(data)
                        
                        # Also migrate predictions if they exist
                        old_pred_ref = db.reference(f'EcoWatch/predictions/{old_id}')
                        predictions = old_pred_ref.get()
                        if predictions:
                            new_pred_ref = db.reference(f'EcoWatch/predictions/{new_id}')
                            new_pred_ref.set(predictions)
                            old_pred_ref.delete()
                        
                        # Delete old sensor
                        old_ref.delete()
                        
                        print(f"   ✅ Migrated: {old_id} → {new_id}")
                    
                except Exception as e:
                    print(f"   ❌ Failed to migrate {old_id}: {e}")
            
            print(f"\n✅ Migration complete!")
    
    else:
        print(f"\n🎉 All sensors already have valid format!")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    import sys
    
    # Initialize Firebase
    initialize_firebase()
    
    # Check command line arguments
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == "--live":
        response = input("⚠️  WARNING: This will modify the database. Continue? (yes/no): ")
        if response.lower() == "yes":
            dry_run = False
        else:
            print("❌ Migration cancelled")
            sys.exit(0)
    
    # Run migration
    migrate_sensors(dry_run=dry_run)
    
    if dry_run:
        print("\n💡 To actually perform the migration, run:")
        print("   python migrate_sensors.py --live")