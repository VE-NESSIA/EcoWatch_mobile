# routers/MLPrediction.py
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from services.ml_service import predict_and_store, predict_and_alert, batch_predict
from services.firebase import get_sensor_data
from ml_models.predictor import get_predictor

router = APIRouter()

class PredictionRequest(BaseModel):
    sensor_id: str
    auto_alert: bool = True  # Automatically send alerts if illegal activity detected


class BatchPredictionRequest(BaseModel):
    sensor_ids: List[str]
    auto_alert: bool = True


@router.post("/ml/predict", tags=["Machine Learning"])
async def predict_sensor_activity(req: PredictionRequest):
    """
    Run ML prediction on latest sensor data
    
    - Fetches latest sensor reading from Firebase
    - Runs ML model prediction
    - Optionally sends alert if illegal mining detected
    - Stores prediction results in Firebase
    
    **Example Request:**
```json
    {
        "sensor_id": "SENSOR_001",
        "auto_alert": true
    }
```
    """
    try:
        # Get latest sensor data
        sensor_data = get_sensor_data(req.sensor_id)
        
        if not sensor_data:
            raise HTTPException(
                status_code=404, 
                detail=f"Sensor {req.sensor_id} not found or has no data"
            )
        
        # Run prediction with optional auto-alert
        result = predict_and_alert(sensor_data, auto_notify=req.auto_alert)
        
        return {
            "sensor_id": req.sensor_id,
            "status": "success",
            **result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")


@router.post("/ml/predict/batch", tags=["Machine Learning"])
async def batch_predict_sensors(req: BatchPredictionRequest):
    """
    Run ML predictions on multiple sensors
    
    **Example Request:**
```json
    {
        "sensor_ids": ["SENSOR_001", "SENSOR_002", "SENSOR_003"],
        "auto_alert": true
    }
```
    """
    try:
        result = batch_predict(req.sensor_ids, auto_notify=req.auto_alert)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch prediction error: {str(e)}")


@router.get("/ml/model/features", tags=["Machine Learning"])
async def get_model_features():
    """
    Get the exact feature names the model was trained with
    """
    try:
        from ml_models.predictor import get_predictor
        predictor = get_predictor()
        
        if hasattr(predictor.model, 'feature_names_in_'):
            feature_names = list(predictor.model.feature_names_in_)
        else:
            feature_names = ["Feature names not available"]
            
        return {
            "total_features": len(feature_names),
            "feature_names": feature_names,
            "model_type": str(type(predictor.model).__name__)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/ml/model/info", tags=["Machine Learning"])
async def get_model_info():
    """
    Get information about the loaded ML model
    
    Returns model configuration, version, and status
    """
    try:
        predictor = get_predictor()
        return {
            "status": "loaded" if predictor.model is not None else "not_loaded",
            "model_path": predictor.model_path,
            "config": predictor.config,
            "model_type": str(type(predictor.model).__name__) if predictor.model else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting model info: {str(e)}")


@router.get("/ml/predictions/{sensor_id}", tags=["Machine Learning"])
async def get_prediction_history(
    sensor_id: str, 
    limit: Optional[int] = Query(10, ge=1, le=100, description="Number of predictions to return")
):
    """
    Get historical ML predictions for a sensor
    
    Returns up to `limit` most recent predictions
    """
    try:
        from firebase_admin import db
        
        predictions_ref = db.reference(f"EcoWatch/predictions/{sensor_id}")
        predictions = predictions_ref.get()
        
        if not predictions:
            return {
                "sensor_id": sensor_id,
                "predictions": [],
                "total": 0,
                "message": "No predictions found for this sensor"
            }
        
        # Convert to list and sort by timestamp
        if isinstance(predictions, dict):
            predictions_list = list(predictions.values())
        else:
            predictions_list = predictions if isinstance(predictions, list) else [predictions]
        
        # Sort by timestamp descending (most recent first)
        predictions_list.sort(
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )
        
        # Apply limit
        predictions_list = predictions_list[:limit]
        
        return {
            "sensor_id": sensor_id,
            "predictions": predictions_list,
            "total": len(predictions_list),
            "limit": limit
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching predictions: {str(e)}")

@router.get("/ml/test/ranges", tags=["Machine Learning"])
async def test_value_ranges():
    """
    Test different value ranges to see what triggers alerts
    Uses CORRECT tiny value ranges from training data
    """
    from ml_models.predictor import get_predictor
    import pandas as pd
    
    predictor = get_predictor()
    
    # Use realistic tiny values matching training data
    test_cases = [
        {"name": "Typical Mining Pattern", "Max_Amplitude": 0.000050, "RMS_Ratio": 1.05, "Power_Ratio": 0.15},
        {"name": "Low Mining Pattern", "Max_Amplitude": 0.000030, "RMS_Ratio": 0.85, "Power_Ratio": 0.10},
        {"name": "High Mining Pattern", "Max_Amplitude": 0.000100, "RMS_Ratio": 1.30, "Power_Ratio": 0.20},
        {"name": "Borderline Low", "Max_Amplitude": 0.000080, "RMS_Ratio": 0.95, "Power_Ratio": 0.18},
        {"name": "Typical Normal", "Max_Amplitude": 0.0015, "RMS_Ratio": 1.25, "Power_Ratio": 0.22},
        {"name": "Low Normal", "Max_Amplitude": 0.0008, "RMS_Ratio": 0.75, "Power_Ratio": 0.12},
        {"name": "High Normal", "Max_Amplitude": 0.0050, "RMS_Ratio": 2.50, "Power_Ratio": 0.40},
        {"name": "Very High Normal", "Max_Amplitude": 0.0100, "RMS_Ratio": 5.00, "Power_Ratio": 0.80},
    ]
    
    results = []
    for test in test_cases:
        df = pd.DataFrame([{
            "Max_Amplitude": test["Max_Amplitude"],
            "RMS_Ratio": test["RMS_Ratio"],
            "Power_Ratio": test["Power_Ratio"]
        }])
        
        pred = predictor.model.predict(df)[0]
        proba = predictor.model.predict_proba(df)[0]
        
        results.append({
            "test_name": test["name"],
            "values": {
                "Max_Amplitude": test["Max_Amplitude"],
                "RMS_Ratio": test["RMS_Ratio"],
                "Power_Ratio": test["Power_Ratio"]
            },
            "prediction": int(pred),
            "label": "✅ Normal" if pred == 0 else "🚨 MINING ALERT",
            "confidence": float(proba[pred]),
            "probabilities": {
                "normal": float(proba[0]),
                "mining": float(proba[1])
            }
        })
    
    return {
        "message": "Testing value ranges with CORRECT tiny values from training data",
        "total_tests": len(results),
        "alerts_detected": sum(1 for r in results if r["prediction"] == 1),
        "results": results
    }

@router.get("/ml/test/from-training-data", tags=["Machine Learning"])
async def test_from_training_samples():
    """
    Test with actual samples from the training data
    This will show us what the model ACTUALLY learned
    """
    from ml_models.predictor import get_predictor
    import pandas as pd
    
    predictor = get_predictor()
    
    # Use exact median/mean values from training stats
    test_cases = [
        # Mining samples - using medians from Label=1
        {"name": "Mining: Median Values", "Max_Amplitude": 0.000040, "RMS_Ratio": 1.014225, "Power_Ratio": 0.143332},
        {"name": "Mining: Mean Values", "Max_Amplitude": 0.000068, "RMS_Ratio": 1.039955, "Power_Ratio": 0.151869},
        {"name": "Mining: 25th Percentile", "Max_Amplitude": 0.000032, "RMS_Ratio": 0.846816, "Power_Ratio": 0.104020},
        {"name": "Mining: 75th Percentile", "Max_Amplitude": 0.000069, "RMS_Ratio": 1.133228, "Power_Ratio": 0.178874},
        {"name": "Mining: Min Values", "Max_Amplitude": 0.000012, "RMS_Ratio": 0.545818, "Power_Ratio": 0.052951},
        {"name": "Mining: Max Values", "Max_Amplitude": 0.000191, "RMS_Ratio": 2.728278, "Power_Ratio": 0.415855},
        
        # Normal samples - using medians from Label=0
        {"name": "Normal: Median Values", "Max_Amplitude": 0.000082, "RMS_Ratio": 0.968781, "Power_Ratio": 0.163087},
        {"name": "Normal: Mean Values", "Max_Amplitude": 0.001533, "RMS_Ratio": 1.216664, "Power_Ratio": 0.220963},
        {"name": "Normal: 25th Percentile", "Max_Amplitude": 0.000040, "RMS_Ratio": 0.735410, "Power_Ratio": 0.118504},
        {"name": "Normal: 75th Percentile", "Max_Amplitude": 0.000236, "RMS_Ratio": 1.162213, "Power_Ratio": 0.261057},
        
        # Edge cases
        {"name": "Very Low Amplitude + High RMS", "Max_Amplitude": 0.000020, "RMS_Ratio": 1.5, "Power_Ratio": 0.10},
        {"name": "Low Amplitude + Low RMS", "Max_Amplitude": 0.000025, "RMS_Ratio": 0.7, "Power_Ratio": 0.08},
        {"name": "Medium Amplitude + Medium RMS", "Max_Amplitude": 0.000100, "RMS_Ratio": 1.0, "Power_Ratio": 0.15},
    ]
    
    results = []
    for test in test_cases:
        df = pd.DataFrame([{
            "Max_Amplitude": test["Max_Amplitude"],
            "RMS_Ratio": test["RMS_Ratio"],
            "Power_Ratio": test["Power_Ratio"]
        }])
        
        pred = predictor.model.predict(df)[0]
        proba = predictor.model.predict_proba(df)[0]
        
        results.append({
            "test_name": test["name"],
            "values": {
                "Max_Amplitude": test["Max_Amplitude"],
                "RMS_Ratio": test["RMS_Ratio"],
                "Power_Ratio": test["Power_Ratio"]
            },
            "prediction": int(pred),
            "label": "✅ Normal" if pred == 0 else "🚨 MINING ALERT",
            "confidence": round(float(proba[pred]), 4),
            "probabilities": {
                "normal": round(float(proba[0]), 4),
                "mining": round(float(proba[1]), 4)
            }
        })
    
    mining_alerts = [r for r in results if r["prediction"] == 1]
    
    return {
        "message": "Testing with actual training data statistics",
        "total_tests": len(results),
        "alerts_detected": len(mining_alerts),
        "mining_alerts": mining_alerts if mining_alerts else "No alerts triggered - model may need retraining",
        "all_results": results
    }

@router.get("/ml/find/threshold", tags=["Machine Learning"])
async def find_mining_threshold():
    """
    Find the exact combination that triggers mining alerts
    """
    from ml_models.predictor import get_predictor
    import pandas as pd
    
    predictor = get_predictor()
    
    # Test very low value combinations systematically
    test_cases = []
    
    # The winning pattern: Very low amplitude + Low RMS + Very low Power
    for amp in [0.000010, 0.000012, 0.000015, 0.000020, 0.000025, 0.000030]:
        for rms in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
            for power in [0.04, 0.05, 0.06, 0.08, 0.10, 0.12]:
                df = pd.DataFrame([{
                    "Max_Amplitude": amp,
                    "RMS_Ratio": rms,
                    "Power_Ratio": power
                }])
                
                pred = predictor.model.predict(df)[0]
                proba = predictor.model.predict_proba(df)[0]
                
                if pred == 1 or proba[1] > 0.3:  # Alert or high suspicion
                    test_cases.append({
                        "Max_Amplitude": amp,
                        "RMS_Ratio": rms,
                        "Power_Ratio": power,
                        "prediction": int(pred),
                        "label": "🚨 ALERT" if pred == 1 else "⚠️ Suspicious",
                        "mining_probability": round(float(proba[1]), 3)
                    })
    
    # Sort by mining probability descending
    test_cases.sort(key=lambda x: x["mining_probability"], reverse=True)
    
    return {
        "message": "Scanning for mining alert patterns",
        "total_scanned": 6 * 6 * 6,  # 216 combinations
        "suspicious_patterns": len(test_cases),
        "alerts_found": sum(1 for t in test_cases if t["prediction"] == 1),
        "top_mining_patterns": test_cases[:20],  # Top 20 highest probabilities
        "alert_threshold": "Mining alerts trigger on VERY LOW values: Amp < 0.00003, RMS < 0.7, Power < 0.1"
    }

    
@router.get("/ml/alerts/summary", tags=["Machine Learning"])
async def get_alerts_summary():
    """
    Get summary of all ML-detected alerts across all sensors
    
    Returns counts of normal vs alert predictions
    """
    try:
        from firebase_admin import db
        
        predictions_ref = db.reference("EcoWatch/predictions")
        all_predictions = predictions_ref.get()
        
        if not all_predictions:
            return {
                "total_predictions": 0,
                "alert_count": 0,
                "normal_count": 0,
                "sensors_with_alerts": []
            }
        
        alert_count = 0
        normal_count = 0
        sensors_with_alerts = set()
        
        for sensor_id, predictions in all_predictions.items():
            if isinstance(predictions, dict):
                for pred in predictions.values():
                    if isinstance(pred, dict):
                        if pred.get("is_alert"):
                            alert_count += 1
                            sensors_with_alerts.add(sensor_id)
                        else:
                            normal_count += 1
        
        return {
            "total_predictions": alert_count + normal_count,
            "alert_count": alert_count,
            "normal_count": normal_count,
            "sensors_with_alerts": list(sensors_with_alerts),
            "alert_percentage": round(alert_count / (alert_count + normal_count) * 100, 2) if (alert_count + normal_count) > 0 else 0
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")