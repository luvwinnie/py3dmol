import asyncio
import threading
import time
import base64
import io
import uuid
import requests
from typing import Optional

import numpy as np
from PIL import Image
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Global server state
_server_instance = None
_server_thread = None
_server_port = 8769

class ImageData(BaseModel):
    request_id: str
    image_data: str
    format: str = "png"
    width: int = 400
    height: int = 300

def is_server_running(port: int = 8769) -> bool:
    """Check if server is already running"""
    try:
        response = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
        return response.status_code == 200
    except:
        return False

class ImageServer:
    def __init__(self, port: int = 8769):
        self.port = port
        self.app = FastAPI(title="Py3DMol Image Server")
        self.pending_requests = {}
        
        # Enable CORS for all origins
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self._setup_routes()
        
    def _setup_routes(self):
        @self.app.post("/convert_image")
        async def convert_image(image_data: ImageData):
            """Convert base64 image data to PIL/numpy format and store for retrieval"""
            try:
                print(f"🔄 Processing image request: {image_data.request_id}")
                print(f"📏 Dimensions: {image_data.width}x{image_data.height}")
                print(f"🎨 Format: {image_data.format}")
                
                # Extract base64 data from data URL
                if ',' in image_data.image_data:
                    base64_data = image_data.image_data.split(',')[1]
                else:
                    base64_data = image_data.image_data
                
                print(f"📊 Base64 data length: {len(base64_data)}")
                
                # Decode base64 to bytes
                image_bytes = base64.b64decode(base64_data)
                print(f"📦 Image bytes length: {len(image_bytes)}")
                
                # Convert to PIL Image
                pil_image = Image.open(io.BytesIO(image_bytes))
                print(f"✅ PIL Image created: {pil_image.size} {pil_image.mode}")
                
                # Store the PIL image for retrieval
                self.pending_requests[image_data.request_id] = {
                    'pil_image': pil_image,
                    'numpy_array': np.array(pil_image),
                    'timestamp': time.time(),
                    'format': image_data.format,
                    'width': image_data.width,
                    'height': image_data.height
                }
                
                print(f"💾 Stored image for request: {image_data.request_id}")
                print(f"📋 Total pending requests: {len(self.pending_requests)}")
                
                return {
                    "status": "success", 
                    "request_id": image_data.request_id,
                    "image_size": pil_image.size,
                    "message": "Image processed and stored successfully"
                }
                
            except Exception as e:
                print(f"❌ Error processing image: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Error processing image: {str(e)}")
        
        @self.app.get("/get_image/{request_id}")
        async def get_image(request_id: str, format: str = "pil"):
            """Retrieve processed image data"""
            print(f"🔍 Looking for request: {request_id}")
            print(f"📋 Available requests: {list(self.pending_requests.keys())}")
            
            if request_id not in self.pending_requests:
                raise HTTPException(status_code=404, detail="Request ID not found")
            
            data = self.pending_requests[request_id]
            print(f"✅ Found request data for: {request_id}")
            
            if format == "pil":
                # Return base64 encoded image data
                img_buffer = io.BytesIO()
                data['pil_image'].save(img_buffer, format='PNG')
                img_bytes = img_buffer.getvalue()
                img_base64 = base64.b64encode(img_bytes).decode()
                
                return {
                    "status": "success",
                    "format": "pil",
                    "image_data": f"data:image/png;base64,{img_base64}",
                    "size": data['pil_image'].size
                }
            elif format == "numpy":
                return {
                    "status": "success", 
                    "format": "numpy",
                    "data": data['numpy_array'].tolist(),
                    "shape": data['numpy_array'].shape
                }
            else:
                raise HTTPException(status_code=400, detail="Format must be 'pil' or 'numpy'")
        
        @self.app.get("/health")
        async def health():
            return {
                "status": "healthy", 
                "port": self.port,
                "pending_requests": list(self.pending_requests.keys())
            }
        
        @self.app.delete("/cleanup/{request_id}")
        async def cleanup_request(request_id: str):
            """Clean up stored image data"""
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]
                return {"status": "cleaned", "request_id": request_id}
            return {"status": "not_found", "request_id": request_id}
    
    def get_stored_image(self, request_id: str, format: str = "pil"):
        """Synchronous method to get stored image data"""
        if request_id not in self.pending_requests:
            return None
        
        data = self.pending_requests[request_id]
        
        if format == "pil":
            return data['pil_image']
        elif format == "numpy":
            return data['numpy_array']
        else:
            return None
    
    def cleanup_old_requests(self, max_age: int = 300):
        """Clean up requests older than max_age seconds"""
        current_time = time.time()
        expired_keys = [
            key for key, value in self.pending_requests.items()
            if current_time - value['timestamp'] > max_age
        ]
        for key in expired_keys:
            del self.pending_requests[key]

def start_server(port: int = 8769) -> ImageServer:
    """Start the FastAPI server in a separate thread"""
    global _server_instance, _server_thread, _server_port
    
    # Check if server is already running on the port
    if is_server_running(port):
        print(f"✅ Py3DMol HTTP server already running on port {port}")
        return _server_instance
    
    # If server is already running in this process, return the existing instance
    if _server_instance is not None and _server_thread is not None and _server_thread.is_alive():
        return _server_instance
    
    _server_port = port
    _server_instance = ImageServer(port)
    
    def run_server():
        try:
            uvicorn.run(_server_instance.app, host="127.0.0.1", port=port, log_level="error")
        except Exception as e:
            print(f"Server error: {e}")
    
    _server_thread = threading.Thread(target=run_server, daemon=True)
    _server_thread.start()
    
    # Wait a bit for the server to start
    time.sleep(1)
    
    return _server_instance

def get_server_instance() -> Optional[ImageServer]:
    """Get the current server instance"""
    return _server_instance

def generate_request_id() -> str:
    """Generate a unique request ID"""
    return str(uuid.uuid4()) 