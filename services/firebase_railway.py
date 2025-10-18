# services/firebase_railway.py
"""
Firebase initialization for Railway deployment
Handles base64-encoded service account credentials
"""
import os
import json
import base64
from firebase_admin import credentials, initialize_app, db as firebase_db

def initialize_firebase_railway():
    """
    Initialize Firebase with Railway environment variables
    Supports both local JSON file and base64-encoded credentials
    """
    try:
        # Check if running on Railway (has RAILWAY_ENVIRONMENT variable)
        if os.getenv("RAILWAY_ENVIRONMENT"):
            print("🚂 Railway environment detected, using base64 credentials...")
            
            # Get base64-encoded service account
            base64_creds = os.getenv("FIREBASE_SERVICE_ACCOUNT_BASE64")
            if not base64_creds:
                raise ValueError("FIREBASE_SERVICE_ACCOUNT_BASE64 not found in Railway environment")
            
            # Decode base64 to JSON
            json_creds = base64.b64decode(base64_creds).decode('utf-8')
            service_account_info = json.loads(json_creds)
            
            # Initialize with decoded credentials
            cred = credentials.Certificate(service_account_info)
        else:
            # Local development - use JSON file
            print("💻 Local environment detected, using JSON file...")
            json_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "firebase-service-account.json")
            cred = credentials.Certificate(json_path)
        
        # Get database URL
        database_url = os.getenv("FIREBASE_DATABASE_URL")
        if not database_url:
            raise ValueError("FIREBASE_DATABASE_URL not set")
        
        # Initialize Firebase
        initialize_app(cred, {
            'databaseURL': database_url
        })
        
        # Test connection
        ref = firebase_db.reference("/")
        ref.get()
        
        print("✅ Firebase initialized successfully")
        print("✅ Database connection test passed")
        
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        raise