from pydantic import BaseModel, Field
from datetime import datetime

class Sensor_data(BaseModel):
    sensor_id: str
    timestamp: datetime
    activity: str= Field(..., description="e.g., vibration, excavation")
    battery: float= Field (..., description="Battery percentage")
    signal_strength:str= Field(..., description="e.g., strong, weak")
    status:str= Field(..., description="e.g., active, inactive")
    isActive:bool = Field(..., description="True if sensor is active")
    isTriggered:bool = Field(..., description="True if sensor is triggered")