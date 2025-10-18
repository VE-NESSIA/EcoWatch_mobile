# EcoWatch API - Production Deployment

## 🌐 Production API

**Base URL:** `https://your-railway-url.up.railway.app`

**API Documentation (Swagger):** `https://your-railway-url.up.railway.app/docs`

**Health Check:** `https://your-railway-url.up.railway.app/health`

---

## 📚 Available Endpoints

### Core Endpoints
```
GET  /                          - API welcome/info
GET  /health                    - Health check
GET  /test                      - Test endpoint
```

### Sensor Management
```
POST /EcoWatch/sensors/{sensor_id}           - Create/Update sensor data (auto-runs ML)
GET  /EcoWatch/sensors/{sensor_id}           - Get sensor data
GET  /EcoWatch/sensors/{sensor_id}/latest    - Get latest reading
GET  /EcoWatch/sensors/{sensor_id}/history   - Get sensor history
```

### ML Predictions
```
POST /ml/predict                              - Run ML prediction manually
POST /ml/predict/batch                        - Batch predictions
GET  /ml/predictions/{sensor_id}              - Get prediction history
GET  /ml/model/info                           - Get model information
GET  /ml/alerts/summary                       - Get alerts summary
```

### Network Information
```
GET  /EcoWatch/info/network-summary           - Get network status & stats
```

### Real-time Streaming
```
GET  /EcoWatch/stream/sensors/{sensor_id}    - SSE stream for sensor
GET  /EcoWatch/stream/sensors                 - SSE stream for all sensors
WS   /ws/sensors/{sensor_id}                  - WebSocket connection
```

### Notifications
```
POST /notification/alerts                     - Send alert notification
```

---

## 🔥 Firebase Configuration

**Project ID:** `ecowatch-d8af5`

**Database URL:** `https://ecowatch-d8af5-default-rtdb.firebaseio.com/`

### Client Config Files (Download from Firebase Console)

**For Android:**
- File: `google-services.json`
- Location: `android/app/google-services.json`

**For iOS:**
- File: `GoogleService-Info.plist`  
- Location: `ios/Runner/GoogleService-Info.plist`

**Download from:** Firebase Console → Project Settings → Your Apps

---

## 📊 ML Model - Mining Detection

### Alert Trigger Values (Stealthy Mining Pattern)

**🚨 Mining Alert Signature:**
```dart
{
  "Max_Amplitude": 0.000012,  // 12 microunits (very subtle)
  "RMS_Ratio": 0.55,          // Low, consistent
  "Power_Ratio": 0.10         // Very low power
}
```

**Expected:** ~58% mining confidence, triggers alert

**✅ Normal Activity:**
```dart
{
  "Max_Amplitude": 0.001000,  // 1000 microunits (larger)
  "RMS_Ratio": 1.00,          // Higher, variable
  "Power_Ratio": 0.20         // Medium power
}
```

**Expected:** <5% mining confidence, no alert

### Value Ranges

| Feature | Mining Range | Normal Range | Unit |
|---------|--------------|--------------|------|
| **Max_Amplitude** | 0.000010 - 0.000012 | 0.000080+ | microunits |
| **RMS_Ratio** | 0.55 - 0.75 | 0.70 - 2.00 | ratio |
| **Power_Ratio** | 0.04 - 0.12 | 0.12 - 0.40 | ratio |

---

## 💻 Flutter Integration Example

### Setup API Service
```dart
// lib/services/ecowatch_api.dart
import 'package:http/http.dart' as http;
import 'dart:convert';

class EcoWatchAPI {
  static const String baseUrl = 'https://your-railway-url.up.railway.app';
  
  /// Create sensor data (auto-runs ML prediction)
  static Future<Map<String, dynamic>> createSensorData({
    required String sensorId,
    required String activity,
    required double battery,
    required String signalStrength,
    required bool isActive,
    required bool isTriggered,
    required double maxAmplitude,
    required double rmsRatio,
    required double powerRatio,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/EcoWatch/sensors/$sensorId'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'sensor_id': sensorId,
        'timestamp': DateTime.now().toIso8601String(),
        'activity': activity,
        'battery': battery,
        'signal_strength': signalStrength,
        'status': 'active',
        'isActive': isActive,
        'isTriggered': isTriggered,
        'Max_Amplitude': maxAmplitude,
        'RMS_Ratio': rmsRatio,
        'Power_Ratio': powerRatio,
      }),
    );
    
    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('Failed to create sensor data: ${response.body}');
    }
  }
  
  /// Get latest sensor reading
  static Future<Map<String, dynamic>> getLatestSensorData(String sensorId) async {
    final response = await http.get(
      Uri.parse('$baseUrl/EcoWatch/sensors/$sensorId/latest'),
    );
    
    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('Failed to load sensor data');
    }
  }
  
  /// Get ML prediction results
  static Future<Map<String, dynamic>> getPredictions(String sensorId) async {
    final response = await http.get(
      Uri.parse('$baseUrl/ml/predictions/$sensorId?limit=10'),
    );
    
    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('Failed to load predictions');
    }
  }
  
  /// Get network summary
  static Future<Map<String, dynamic>> getNetworkSummary() async {
    final response = await http.get(
      Uri.parse('$baseUrl/EcoWatch/info/network-summary'),
    );
    
    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('Failed to load network summary');
    }
  }
}
```

### Usage Example
```dart
// Example: Submit sensor reading
try {
  final result = await EcoWatchAPI.createSensorData(
    sensorId: 'SENSOR_001',
    activity: 'vibration',
    battery: 85.5,
    signalStrength: 'strong',
    isActive: true,
    isTriggered: false,
    maxAmplitude: 0.001000,  // Normal activity
    rmsRatio: 1.00,
    powerRatio: 0.20,
  );
  
  print('Sensor data submitted: $result');
  // Backend automatically runs ML prediction and stores results
  
} catch (e) {
  print('Error: $e');
}

// Example: Check for mining alerts
try {
  final predictions = await EcoWatchAPI.getPredictions('SENSOR_001');
  
  for (var prediction in predictions['predictions']) {
    if (prediction['is_alert']) {
      // Show alert to user
      print('🚨 Mining Alert: ${prediction['class_label']}');
      print('Confidence: ${prediction['confidence']}');
    }
  }
} catch (e) {
  print('Error: $e');
}
```

### Real-time Updates with SSE
```dart
// lib/services/realtime_service.dart
import 'package:flutter_sse/flutter_sse.dart';
import 'dart:convert';

class RealtimeService {
  static const String baseUrl = 'https://your-railway-url.up.railway.app';
  
  Stream<Map<String, dynamic>> listenToSensor(String sensorId) {
    return SSEClient.subscribeToSSE(
      method: SSERequestType.GET,
      url: '$baseUrl/EcoWatch/stream/sensors/$sensorId',
      header: {
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    ).map((event) {
      return json.decode(event.data ?? '{}');
    });
  }
}

// Usage in widget
StreamBuilder<Map<String, dynamic>>(
  stream: RealtimeService().listenToSensor('SENSOR_001'),
  builder: (context, snapshot) {
    if (snapshot.hasData) {
      final data = snapshot.data!;
      return Text('Battery: ${data['battery']}%');
    }
    return CircularProgressIndicator();
  },
)
```

---

## 🔐 Required Flutter Packages

Add to `pubspec.yaml`:
```yaml
dependencies:
  flutter:
    sdk: flutter
  
  # HTTP & API
  http: ^1.1.0
  
  # Firebase
  firebase_core: ^2.24.0
  firebase_messaging: ^14.7.0  # For push notifications
  
  # Real-time updates
  flutter_sse: ^1.0.0  # For Server-Sent Events
  
  # Optional
  provider: ^6.1.0  # State management
```

---

## 🧪 Testing the API

### Test in Browser
1. Health: `https://your-railway-url.up.railway.app/health`
2. Docs: `https://your-railway-url.up.railway.app/docs`
3. Test endpoint: `https://your-railway-url.up.railway.app/test`

### Test with Postman or cURL
```bash
# Health check
curl https://your-railway-url.up.railway.app/health

# Create sensor data
curl -X POST https://your-railway-url.up.railway.app/EcoWatch/sensors/TEST_001 \
  -H "Content-Type: application/json" \
  -d '{
    "sensor_id": "TEST_001",
    "timestamp": "2025-10-19T12:00:00",
    "activity": "idle",
    "battery": 95.0,
    "signal_strength": "strong",
    "status": "active",
    "isActive": true,
    "isTriggered": false,
    "Max_Amplitude": 0.001000,
    "RMS_Ratio": 1.00,
    "Power_Ratio": 0.20
  }'
```

---

## 📞 Support & Documentation

**API Documentation:** Use Swagger UI at `/docs` for interactive testing

**Backend Repository:** [Your GitHub Repo Link]

**Issues/Questions:** [Your Contact Email]

---

## ⚠️ Important Notes

1. **All sensor data submissions automatically trigger ML predictions**
2. **Mining alerts are stored in Firebase under** `EcoWatch/predictions/{sensor_id}`
3. **Push notifications require FCM tokens** stored in Firebase
4. **The model detects subtle, stealthy mining patterns** (not loud explosions)
5. **Use the exact value ranges for accurate ML detection**

---

## 🚀 Getting Started Checklist

- [ ] Add Firebase config files to Flutter project
- [ ] Install required packages (`flutter pub get`)
- [ ] Update API base URL in Flutter code
- [ ] Test health endpoint
- [ ] Test sensor data submission
- [ ] Verify ML predictions working
- [ ] Setup FCM for push notifications
- [ ] Test real-time streaming (optional)
- [ ] Deploy Flutter app!

---

**API Version:** 2.0.0  
**Last Updated:** October 19, 2025  
**Status:** ✅ Production Ready
```

---

## 📦 Step 4: Get Firebase Config Files

### **Download from Firebase Console:**

1. **Go to:** https://console.firebase.google.com/project/ecowatch-d8af5/settings/general

2. **For Android:**
   - Scroll to "Your apps"
   - Click on **Android app** (ecowatch_mobile)
   - Click **"google-services.json"** button
   - Download and save

3. **For iOS:**
   - Click on **iOS app** (ecowatch_mobile)
   - Click **"GoogleService-Info.plist"** button
   - Download and save

