# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# Get port from environment (Railway requirement)
PORT = int(os.getenv("PORT", 8000))

app = FastAPI(
    title="EcoWatch API",
    description="Sensor Monitoring System with ML-Powered Illegal Mining Detection",
    version="2.0.0"
)

# ✅ SIMPLIFIED CORS for Mobile App
# Mobile apps don't have CORS restrictions (only web browsers do)
# We use "*" for simplicity since mobile clients can connect from anywhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (perfect for mobile apps)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)

print("🚀 DEBUG: Starting router import...")

# Load all routers
routers_config = [
    ("routers.AlertScreen", "router", "AlertScreen"),
    ("routers.HomeScreen", "router", "HomeScreen"),
    ("routers.InfoScreen", "router", "InfoScreen"),
    ("routers.SensorProfile", "router", "SensorProfile"),
    ("routers.RealtimeStream", "router", "RealtimeStream"),
    ("routers.MLPrediction", "router", "MLPrediction"),
]

for module_path, router_name, display_name in routers_config:
    try:
        module = __import__(module_path, fromlist=[router_name])
        router = getattr(module, router_name)
        app.include_router(router)
        print(f"✅ SUCCESS: {display_name} router loaded")
        
        for route in router.routes:
            methods = list(route.methods) if hasattr(route, 'methods') else ['WS']
            print(f"   Route: {methods} {route.path}")
    except Exception as e:
        print(f"❌ FAILED: {display_name} - {e}")
        import traceback
        traceback.print_exc()

# Health check endpoints
@app.get("/", tags=["Core"])
async def root():
    """API root endpoint"""
    return {
        "message": "EcoWatch API with ML Detection is running!",
        "version": "2.0.0",
        "features": [
            "Sensor Monitoring",
            "Real-time Streaming (SSE/WebSocket)",
            "ML-Powered Mining Detection",
            "Push Notifications",
            "Historical Analytics"
        ],
        "documentation": "/docs",
        "status": "operational"
    }

@app.get("/test", tags=["Core"])
async def test_endpoint():
    """Simple test endpoint"""
    return {
        "status": "success",
        "message": "Test endpoint works!",
        "timestamp": "2025-10-18T00:00:00Z"
    }

@app.get("/health", tags=["Core"])
async def health_check():
    """
    Health check endpoint
    
    Verifies:
    - API is running
    - ML model is loaded
    - Firebase connection (basic check)
    """
    health_status = {
        "status": "healthy",
        "service": "EcoWatch API",
        "version": "2.0.0"
    }
    
    # Check ML model
    try:
        from ml_models.predictor import get_predictor
        predictor = get_predictor()
        health_status["ml_model"] = "loaded" if predictor.model is not None else "not_loaded"
    except Exception as e:
        health_status["ml_model"] = f"error: {str(e)}"
    
    # Check Firebase connection
    try:
        from firebase_admin import db
        ref = db.reference("/")
        ref.get()  # Simple connection test
        health_status["firebase"] = "connected"
    except Exception as e:
        health_status["firebase"] = f"error: {str(e)}"
    
    return health_status

if __name__ == "__main__":
    import uvicorn
    print(f"\n🚀 Starting EcoWatch API server on port {PORT}...")
    print(f"📚 API Docs: http://127.0.0.1:{PORT}/docs")
    print(f"🏠 Root: http://127.0.0.1:{PORT}/")
    print(f"❤️  Health: http://127.0.0.1:{PORT}/health")
    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=True)