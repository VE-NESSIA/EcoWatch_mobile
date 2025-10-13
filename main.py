from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import db

app = FastAPI(
    title="EcoWatch API",
    description="Sensor Monitoring System",
    version="1.0.0"
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("DEBUG: Starting router import...")

# Test each router individually
try:
    from routers.AlertScreen import router as alert_router
    app.include_router(alert_router)
    print("SUCCESS: AlertScreen router loaded")
    
    # Test if routes exist
    for route in alert_router.routes:
        print(f"   Route: {list(route.methods)} {route.path}")
except Exception as e:
    print(f" FAILED: AlertScreen - {e}")

try:
    from routers.HomeScreen import router as home_router
    app.include_router(home_router)
    print("SUCCESS: HomeScreen router loaded")
    
    for route in home_router.routes:
        print(f"   Route: {list(route.methods)} {route.path}")
except Exception as e:
    print(f" FAILED: HomeScreen - {e}")

try:
    from routers.InfoScreen import router as info_router
    app.include_router(info_router)
    print("SUCCESS: InfoScreen router loaded")
    
    for route in info_router.routes:
        print(f"    Route: {list(route.methods)} {route.path}")
except Exception as e:
    print(f" FAILED: InfoScreen - {e}")

try:
    from routers.SensorProfile import router as sensor_router
    app.include_router(sensor_router)
    print("SUCCESS: SensorProfile router loaded")
    
    for route in sensor_router.routes:
        print(f"  Route: {list(route.methods)} {route.path}")
except Exception as e:
    print(f"FAILED: SensorProfile - {e}")

# Add a simple test endpoint that will definitely work
@app.get("/")
async def root():
    return {
        "message": "EcoWatch API is running!",
        "status": "Check console for loaded routes"
    }

@app.get("/debug-test")
async def test_endpoint():
    return {"message": "Test endpoint works!"}

@app.get("/debug-health")
async def health_check():
    return {"status": "healthy", "service": "EcoWatch API"}

if __name__ == "_main_":
    import uvicorn
    print("\n Starting server...")
    print("Docs will be at: http://127.0.0.1:8000/docs")
    print("Root endpoint: http://127.0.0.1:8000/")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)