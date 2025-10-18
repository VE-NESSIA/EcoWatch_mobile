# routers/RealtimeStream.py
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from firebase_admin import db
from typing import AsyncGenerator, Optional
import json
import asyncio
from datetime import datetime

router = APIRouter()

# Store for active listeners
active_listeners = {}

def firebase_listener_callback(sensor_id: str, event_queue: asyncio.Queue):
    """Callback function for Firebase real-time listener"""
    def on_change(event):
        try:
            # Put the change into the async queue
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                event_queue.put_nowait,
                {
                    "sensor_id": sensor_id,
                    "data": event.data,
                    "path": event.path,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            print(f"Error in listener callback: {e}")
    return on_change


async def event_generator(sensor_id: Optional[str] = None) -> AsyncGenerator[str, None]:
    """
    Generate Server-Sent Events for real-time updates
    Listens to Firebase changes and streams them to client
    """
    event_queue = asyncio.Queue()
    listener = None
    
    try:
        # Setup Firebase listener
        if sensor_id:
            # Listen to specific sensor
            ref = db.reference(f"EcoWatch/sensors/{sensor_id}")
            yield f"data: {json.dumps({'status': 'connected', 'sensor_id': sensor_id})}\n\n"
        else:
            # Listen to all sensors
            ref = db.reference("EcoWatch/sensors")
            yield f"data: {json.dumps({'status': 'connected', 'listening': 'all_sensors'})}\n\n"
        
        listener = ref.listen(firebase_listener_callback(sensor_id or "all", event_queue))
        
        # Stream events as they come
        while True:
            try:
                # Wait for new data from Firebase with timeout
                data = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                
                # Format as SSE
                yield f"data: {json.dumps(data)}\n\n"
                
            except asyncio.TimeoutError:
                # Send heartbeat every 30 seconds to keep connection alive
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e), 'type': 'error'})}\n\n"
        
    finally:
        # Cleanup listener when client disconnects
        if listener:
            ref.close()


@router.get("/EcoWatch/stream/sensors/{sensor_id}", tags=["Real-time Streaming"])
async def stream_sensor_data(sensor_id: str):
    """
    Stream real-time updates for a specific sensor using Server-Sent Events (SSE)
    
    **Usage in Flutter:**
```dart
    import 'package:flutter_sse/flutter_sse.dart';
    
    SSEClient.subscribeToSSE(
      url: 'http://your-api.com/EcoWatch/stream/sensors/SENSOR_001',
      header: {"Accept": "text/event-stream"}
    ).listen((event) {
      print('Data: ${event.data}');
    });
```
    
    **Connection stays open and pushes updates automatically**
    """
    return StreamingResponse(
        event_generator(sensor_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering in nginx
        }
    )


@router.get("/EcoWatch/stream/sensors", tags=["Real-time Streaming"])
async def stream_all_sensors():
    """
    Stream real-time updates for ALL sensors using Server-Sent Events (SSE)
    
    **Usage in Flutter:**
```dart
    SSEClient.subscribeToSSE(
      url: 'http://your-api.com/EcoWatch/stream/sensors',
      header: {"Accept": "text/event-stream"}
    ).listen((event) {
      var data = jsonDecode(event.data!);
      print('Sensor: ${data['sensor_id']}, Data: ${data['data']}');
    });
```
    """
    return StreamingResponse(
        event_generator(None),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# Alternative: WebSocket implementation
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, sensor_id: str):
        await websocket.accept()
        if sensor_id not in self.active_connections:
            self.active_connections[sensor_id] = set()
        self.active_connections[sensor_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, sensor_id: str):
        if sensor_id in self.active_connections:
            self.active_connections[sensor_id].discard(websocket)
    
    async def broadcast(self, sensor_id: str, message: dict):
        if sensor_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[sensor_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.add(connection)
            
            # Clean up disconnected clients
            for conn in disconnected:
                self.active_connections[sensor_id].discard(conn)

manager = ConnectionManager()

@router.websocket("/ws/sensors/{sensor_id}")
async def websocket_sensor_endpoint(websocket: WebSocket, sensor_id: str):
    """
    WebSocket endpoint for real-time sensor updates
    
    **Usage in Flutter with web_socket_channel:**
```dart
    import 'package:web_socket_channel/web_socket_channel.dart';
    
    final channel = WebSocketChannel.connect(
      Uri.parse('ws://your-api.com/ws/sensors/SENSOR_001'),
    );
    
    channel.stream.listen((message) {
      var data = jsonDecode(message);
      print('Received: $data');
    });
```
    """
    await manager.connect(websocket, sensor_id)
    
    # Setup Firebase listener
    def on_change(event):
        try:
            asyncio.create_task(manager.broadcast(sensor_id, {
                "sensor_id": sensor_id,
                "data": event.data,
                "timestamp": datetime.utcnow().isoformat()
            }))
        except Exception as e:
            print(f"Broadcast error: {e}")
    
    ref = db.reference(f"EcoWatch/sensors/{sensor_id}")
    listener = ref.listen(on_change)
    
    try:
        while True:
            # Keep connection alive and receive messages from client
            data = await websocket.receive_text()
            # Echo back for testing
            await websocket.send_json({
                "received": data,
                "timestamp": datetime.utcnow().isoformat()
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket, sensor_id)
        ref.close()
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, sensor_id)
        ref.close()