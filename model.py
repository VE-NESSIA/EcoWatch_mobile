# model.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional
import re

class Sensor_data(BaseModel):
    sensor_id: str = Field(..., description="Sensor ID in format SNR-XXX (dynamically scaled)")
    timestamp: datetime
    activity: str
    battery: float
    signal_strength: str
    status: str
    isActive: bool
    isTriggered: bool
    
    # ML Features
    Max_Amplitude: Optional[float] = None
    RMS_Ratio: Optional[float] = None
    Power_Ratio: Optional[float] = None
    
    @field_validator('sensor_id')
    @classmethod
    def validate_sensor_id(cls, v: str) -> str:
        """
        Validate sensor ID format: SNR-XXX with dynamic length
        
        Accepts:
        - SNR-001 through SNR-999 (3 digits)
        - SNR-1000 through SNR-9999 (4 digits)  
        - SNR-10000+ (5+ digits, scales infinitely)
        
        Examples:
        - SNR-001 ✓
        - SNR-999 ✓
        - SNR-1000 ✓
        - SNR-10000 ✓
        - SNR-100000 ✓
        """
        # Pattern: SNR- followed by at least 3 digits
        pattern = r'^SNR-\d{3,}$'
        
        if not re.match(pattern, v):
            raise ValueError(
                f'Sensor ID must match format SNR-XXX (at least 3 digits). '
                f'Examples: SNR-001, SNR-1000, SNR-10000. Got: {v}'
            )
        
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "sensor_id": "SNR-001",
                "timestamp": "2025-10-19T12:00:00",
                "activity": "vibration",
                "battery": 85.5,
                "signal_strength": "strong",
                "status": "active",
                "isActive": True,
                "isTriggered": False,
                "Max_Amplitude": 0.000012,
                "RMS_Ratio": 0.55,
                "Power_Ratio": 0.10
            }
        }