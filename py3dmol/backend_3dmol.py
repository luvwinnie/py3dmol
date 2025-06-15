import json
import time
import base64
import requests
import uuid
from io import BytesIO
from typing import Optional, Union
import os

try:
    from cStringIO import StringIO  # Python 2.x
except ImportError:
    from io import StringIO  # Python 3.x

try:
    from IPython.display import HTML, display, Javascript
    import IPython.display as ipyd
    from IPython import get_ipython
    HAS_IPYTHON = True
    HAS_IPYTHON_KERNEL = True
except ImportError:
    HAS_IPYTHON = False
    HAS_IPYTHON_KERNEL = False
    # Create dummy functions for non-IPython environments
    class Javascript:
        def __init__(self, code):
            pass
    
    class HTML:
        def __init__(self, content):
            pass
    
    def display(obj):
        pass
    
    def get_ipython():
        return None
    
    class ipyd:
        @staticmethod
        def display(obj):
            pass

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# Try to import and initialize 3Dmol.js
try:
    import pkg_resources
    try:
        _3dmol_js = pkg_resources.resource_string(__name__, "3Dmol-min.js").decode("utf-8")
    except (FileNotFoundError, AttributeError):
        # Fallback for development or if package resource is not available
        import os
        module_dir = os.path.dirname(__file__)
        # Try both the minified and non-minified versions
        for js_filename in ["3Dmol-min.js", "3dmol.js"]:
            js_path = os.path.join(module_dir, js_filename)
            if os.path.exists(js_path):
                with open(js_path, 'r') as f:
                    _3dmol_js = f.read()
                print(f"✅ Loaded local 3DMol.js from: {js_path}")
                break
        else:
            _3dmol_js = ""
            print("⚠️  No local 3DMol.js file found")
    _imported_3dmol = True
except (ImportError, FileNotFoundError, AttributeError):
    _3dmol_js = ""
    _imported_3dmol = True

def _is_jupyter_environment() -> bool:
    """Check if we're running in a Jupyter notebook environment"""
    if not HAS_IPYTHON_KERNEL:
        return False
    
    try:
        # Check if we're in IPython and have a display backend
        ipy = get_ipython()
        if ipy is None:
            return False
            
        # Check if we have display capabilities
        return hasattr(ipy, 'display') or 'IPKernelApp' in ipy.config
    except:
        return False

def _is_headless_environment() -> bool:
    """Check if we're in a headless environment (no display)"""
    # Check for common headless indicators
    if os.environ.get('DISPLAY') is None and os.name != 'nt':  # Unix without display
        return True
    if os.environ.get('TERM') == 'dumb':  # Dumb terminal
        return True
    return not _is_jupyter_environment()

class JS3DMol(object):
    """
    JS3DMol object for Jupyter notebook integration
    """

    def __init__(self, width=400, height=400, id=None):
        """
        Initialize viewer
        
        Args:
            width: Width of viewer
            height: Height of viewer
            id: Optional viewer ID
        """
        self.width = width
        self.height = height
        self.id = id if id else f'viewer_{int(time.time() * 1000)}'
        self.commands = []
        
        if not HAS_IPYTHON:
            print("⚠️  Running without IPython - display capabilities limited")

    def _test_server_connectivity(self):
        """Test if the FastAPI server is accessible"""
        try:
            response = requests.get("http://localhost:8769/health", timeout=2)
            if response.status_code == 200:
                print("✅ FastAPI server is accessible")
                return True
            else:
                print(f"❌ Server responded with status: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Cannot connect to FastAPI server: {e}")
            return False

    def executeCode(self, code):
        """Execute JavaScript code in the viewer context"""
        if not HAS_IPYTHON:
            print("⚠️  JavaScript execution not available without IPython")
            return
        
        # Store the command for later execution
        self.commands.append(code)
        
        # Don't execute immediately - commands will be executed when show() is called
        # This prevents the infinite "Waiting for 3Dmol.js to load..." messages

    def _execute_queued_commands(self):
        """Execute all queued commands after the viewer is created"""
        if not self.commands:
            return
        
        # Create JavaScript to execute all commands at once
        combined_js = []
        for i, command in enumerate(self.commands):
            combined_js.append(f"// Command {i+1}")
            combined_js.append(command)
        
        # Wrap all commands in a function that waits for viewer to be ready with timeout
        wrapped_code = f"""
        (function() {{
            console.log('🚀 Executing {len(self.commands)} queued commands for viewer: {self.id}');
            
            var maxAttempts = 50; // Maximum 10 seconds (50 * 200ms)
            var attempts = 0;
            
            function executeWhenReady() {{
                attempts++;
                
                // Check if we've exceeded maximum attempts
                if (attempts > maxAttempts) {{
                    console.error('❌ Timeout waiting for 3Dmol viewer to be ready');
                    console.error('❌ Last state: $3Dmol=' + (typeof $3Dmol) + ', viewer=' + (window.py3dmol_viewer_ready ? window.py3dmol_viewer_ready['{self.id}'] : 'undefined'));
                    return;
                }}
                
                // Check if all dependencies are available
                if (typeof $3Dmol === 'undefined') {{
                    if (attempts === 1 || attempts % 10 === 0) {{
                        console.log('⏳ Waiting for 3Dmol.js to load... (attempt ' + attempts + '/' + maxAttempts + ')');
                    }}
                    setTimeout(executeWhenReady, 200);
                    return;
                }}
                
                if (typeof $ === 'undefined') {{
                    console.log('⏳ Waiting for jQuery to load...');
                    setTimeout(executeWhenReady, 200);
                    return;
                }}
                
                if (!$3Dmol.viewers || !$3Dmol.viewers['{self.id}']) {{
                    if (attempts === 1 || attempts % 10 === 0) {{
                        console.log('⏳ Waiting for viewer to be created... (attempt ' + attempts + '/' + maxAttempts + ')');
                    }}
                    setTimeout(executeWhenReady, 200);
                    return;
                }}
                
                if (!window.py3dmol_viewer_ready || !window.py3dmol_viewer_ready['{self.id}']) {{
                    if (attempts === 1 || attempts % 10 === 0) {{
                        console.log('⏳ Waiting for viewer to be ready... (attempt ' + attempts + '/' + maxAttempts + ')');
                    }}
                    setTimeout(executeWhenReady, 200);
                    return;
                }}
                
                // All dependencies ready, execute all commands
                try {{
                    console.log('✅ Executing all commands...');
                    {'; '.join(combined_js)}
                    console.log('✅ All commands executed successfully');
                }} catch (error) {{
                    console.error('❌ Error executing commands:', error);
                }}
            }}
            
            // Start execution with a delay to allow viewer initialization
            setTimeout(executeWhenReady, 1000);
        }})();
        """
        
        ipyd.display(Javascript(wrapped_code))

    def get_image_data(self, format='png', width=None, height=None, antialias=True, force_headless=False):
        """
        Get image data from the viewer
        
        Args:
            format: Image format ('png' or 'jpeg')
            width: Image width (defaults to viewer width)
            height: Image height (defaults to viewer height)
            antialias: Enable antialiasing
            force_headless: Force headless capture even in Jupyter (bypasses JavaScript issues)
            
        Returns:
            Base64 encoded image data string or None if failed
        """
        print(f"🔧 get_image_data() - Auto-detecting environment...")
        
        # Check if headless mode is forced
        if force_headless:
            print("🖥️  Forced headless mode - using headless capture method")
            return self._get_image_data_headless(format, width, height, antialias)
        
        # Auto-detect environment and use appropriate method
        if _is_jupyter_environment():
            print("🌐 Jupyter environment detected - using FastAPI server method")
            result = self._get_image_data_fastapi(format, width, height, antialias)
            
            # If FastAPI method fails, fallback to headless
            if result is None:
                print("⚠️  FastAPI method failed, falling back to headless capture...")
                return self._get_image_data_headless(format, width, height, antialias)
            return result
        else:
            print("🖥️  Headless environment detected - using headless capture method")
            return self._get_image_data_headless(format, width, height, antialias)

    def _get_image_data_fastapi(self, format='png', width=None, height=None, antialias=True):
        """Get image data using FastAPI server method (for Jupyter environments)"""
        # Check if server is available
        if not self._test_server_connectivity():
            return None
            
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        
        # Use default dimensions if not specified
        if width is None:
            width = self.width
        if height is None:
            height = self.height
            
        # Create the JavaScript code to capture image
        js_code = f"""
        (function() {{
            console.log('🔧 Starting image capture with FastAPI method');
            console.log('📊 Request ID: {request_id}');
            console.log('📏 Dimensions: {width}x{height}');
            
            // Function to find the viewer
            function findViewer() {{
                console.log('🔍 Looking for 3DMol viewer...');
                
                // Try to find viewer by ID first
                if (window.$3Dmol && window.$3Dmol.viewers) {{
                    console.log('✅ $3Dmol.viewers found:', Object.keys(window.$3Dmol.viewers));
                    
                    // Try specific viewer ID
                    if (window.$3Dmol.viewers['{self.id}']) {{
                        console.log('✅ Found viewer by ID: {self.id}');
                        return window.$3Dmol.viewers['{self.id}'];
                    }}
                    
                    // Try first available viewer
                    var viewerKeys = Object.keys(window.$3Dmol.viewers);
                    if (viewerKeys.length > 0) {{
                        var firstKey = viewerKeys[0];
                        console.log('✅ Using first available viewer:', firstKey);
                        return window.$3Dmol.viewers[firstKey];
                    }}
                }}
                
                console.log('❌ No 3DMol viewers found');
                return null;
            }}
            
            // Function to capture and send image
            function captureAndSend() {{
                var viewer = findViewer();
                
                if (!viewer) {{
                    console.error('❌ No 3DMol viewer found');
                    return;
                }}
                
                try {{
                    console.log('🎨 Rendering viewer...');
                    viewer.render();
                    
                    // Wait for rendering to complete and ensure proper canvas size
                    setTimeout(function() {{
                        try {{
                            // First ensure the viewer container has proper size
                            var container = document.getElementById('{self.id}');
                            if (container) {{
                                container.style.width = '{width}px';
                                container.style.height = '{height}px';
                                viewer.resize();
                                viewer.render();
                                console.log('🔄 Resized viewer container to {width}x{height}');
                            }}
                            
                            // Wait a bit more after resize
                            setTimeout(function() {{
                                console.log('📷 Getting canvas...');
                                var canvas = viewer.getCanvas();
                            
                                if (!canvas) {{
                                    console.error('❌ Could not get canvas from viewer');
                                    return;
                                }}
                                
                                console.log('✅ Canvas obtained:', canvas.width, 'x', canvas.height);
                                
                                // Check if canvas has valid size
                                if (canvas.width === 0 || canvas.height === 0) {{
                                    console.error('❌ Canvas has zero size - this will cause capture to fail');
                                    return;
                                }}
                                
                                // Convert to base64
                                var imageData = canvas.toDataURL('image/{format}');
                                console.log('✅ Image data captured, length:', imageData.length);
                                
                                if (imageData.length < 100) {{
                                    console.error('❌ Image data too short, likely empty canvas');
                                    return;
                                }}
                                
                                // Send to FastAPI server
                                console.log('📤 Sending to FastAPI server...');
                                fetch('http://localhost:8769/convert_image', {{
                                    method: 'POST',
                                    headers: {{
                                        'Content-Type': 'application/json',
                                    }},
                                    body: JSON.stringify({{
                                        request_id: '{request_id}',
                                        image_data: imageData,
                                        format: '{format}',
                                        width: {width},
                                        height: {height}
                                    }})
                                }})
                                .then(response => {{
                                    console.log('📨 Server response status:', response.status);
                                    if (!response.ok) {{
                                        throw new Error('Server responded with status: ' + response.status);
                                    }}
                                    return response.json();
                                }})
                                .then(data => {{
                                    console.log('✅ Image sent to FastAPI server successfully:', data);
                                    window.py3dmol_last_capture = {{
                                        request_id: '{request_id}',
                                        status: 'success',
                                        timestamp: Date.now()
                                    }};
                                }})
                                .catch(error => {{
                                    console.error('❌ Error sending to FastAPI:', error);
                                    window.py3dmol_last_capture = {{
                                        request_id: '{request_id}',
                                        status: 'error',
                                        error: error.message,
                                        timestamp: Date.now()
                                    }};
                                }});
                                
                            }}, 500);
                            
                        }} catch (canvasError) {{
                            console.error('❌ Error getting canvas data:', canvasError);
                        }}
                    }}, 1000); // Wait 1 second for rendering
                    
                }} catch (error) {{
                    console.error('❌ Error in capture process:', error);
                }}
            }}
            
            // Start the capture process
            if (window.$3Dmol) {{
                console.log('✅ 3DMol library is available');
                captureAndSend();
            }} else {{
                console.error('❌ 3DMol library not found');
            }}
        }})();
        """
        
        # Execute JavaScript
        display(Javascript(js_code))
        
        # Wait for the image to be processed
        print(f"⏳ Waiting for image capture (request ID: {request_id}...)")
        time.sleep(5)  # Increased wait time for proper rendering
        
        # Check JavaScript status
        status_check_js = """
        if (window.py3dmol_last_capture) {
            console.log('🔍 Last capture status:', window.py3dmol_last_capture);
        } else {
            console.log('❌ No capture status found');
        }
        """
        display(Javascript(status_check_js))
        
        # Retrieve the image from the server
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                response = requests.get(f'http://localhost:8769/get_image/{request_id}', timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'success':
                        print(f"✅ Image data retrieved successfully")
                        return data['image_data']
                    else:
                        print(f"❌ Server error: {data.get('message', 'Unknown error')}")
                elif response.status_code == 404:
                    print(f"🔍 Request not found, attempt {attempt + 1}/{max_attempts}")
                    time.sleep(1)
                else:
                    print(f"❌ Server error: {response.status_code}")
                    
            except requests.RequestException as e:
                print(f"❌ Request error: {e}")
                break
        
        # Debug: Check what's on the server
        try:
            debug_response = requests.get('http://localhost:8769/health', timeout=5)
            if debug_response.status_code == 200:
                server_data = debug_response.json()
                print(f"🔍 Checking server for request ID: {request_id}...")
                print(f"📊 Server has {len(server_data.get('pending_requests', []))} pending requests")
                if len(server_data.get('pending_requests', [])) == 0:
                    print("❌ Request NOT found in server")
                else:
                    print(f"🔧 Available request IDs: {server_data.get('pending_requests', [])[:3]}...")
        except:
            pass
        
        print("✗ Failed to retrieve image from server")
        print("💡 Check browser console (F12) for detailed JavaScript errors")
        return None

    def _get_image_data_headless(self, format='png', width=None, height=None, antialias=True):
        """Get image data using headless capture method (for terminal/headless environments)"""
        try:
            from .headless_capture import capture_headless_image, is_headless_available
            
            if not is_headless_available():
                print("❌ Headless capture not available")
                print("💡 Install selenium: pip install selenium webdriver-manager")
                return None
                
            # Use default dimensions if not specified
            if width is None:
                width = self.width
            if height is None:
                height = self.height
                
            print(f"🔧 Using headless capture: {width}x{height}, format: {format}")
            
            # Capture image using headless method
            image_data = capture_headless_image(self, width, height, format)
            
            if image_data:
                print("✅ Headless capture successful")
                return image_data
            else:
                print("❌ Headless capture failed")
                return None
                
        except ImportError as e:
            print(f"❌ Headless capture dependencies not available: {e}")
            print("💡 Install selenium: pip install selenium webdriver-manager")
            return None

    def get_pil_image(self, img_format='png', width=None, height=None, antialias=True, force_headless=False):
        """
        Get PIL Image object from the viewer
        
        Args:
            format: Image format ('png' or 'jpeg')
            width: Image width (defaults to viewer width)
            height: Image height (defaults to viewer height)
            antialias: Enable antialiasing
            force_headless: Force headless capture even in Jupyter (bypasses JavaScript issues)
            
        Returns:
            PIL Image object or None if failed
        """
        if not HAS_PIL:
            print("❌ PIL not available. Install with: pip install pillow")
            return None
            
        # Get image data
        image_data = self.get_image_data(img_format, width, height, antialias, force_headless)
        
        if not image_data:
            return None
            
        try:
            # Remove data URL prefix if present
            if image_data.startswith('data:'):
                image_data = image_data.split(',')[1]
            
            # Decode base64 to bytes
            image_bytes = base64.b64decode(image_data)
            
            # Create PIL Image
            image = Image.open(BytesIO(image_bytes))
            print(f"✅ PIL Image created: {image.size} {image.mode}")
            return image
            
        except Exception as e:
            print(f"❌ Error creating PIL image: {e}")
            return None

    def get_numpy_image(self, img_format='png', width=None, height=None, antialias=True, force_headless=False):
        """
        Get NumPy array from the viewer
        
        Args:
            format: Image format ('png' or 'jpeg')
            width: Image width (defaults to viewer width)
            height: Image height (defaults to viewer height)
            antialias: Enable antialiasing
            force_headless: Force headless capture even in Jupyter (bypasses JavaScript issues)
            
        Returns:
            NumPy array (H, W, C) or None if failed
        """
        if not HAS_NUMPY:
            print("❌ NumPy not available. Install with: pip install numpy")
            return None

        # Get PIL image first
        pil_image = self.get_pil_image(img_format, width, height, antialias, force_headless)
        
        if not pil_image:
            return None
        
        try:
            # Convert PIL to NumPy array
            if pil_image.mode == 'RGBA':
                numpy_array = np.array(pil_image)
            elif pil_image.mode == 'RGB':
                numpy_array = np.array(pil_image)
            else:
                # Convert to RGB first
                pil_image = pil_image.convert('RGB')
                numpy_array = np.array(pil_image)
            
            print(f"✅ NumPy array created: {numpy_array.shape} {numpy_array.dtype}")
            return numpy_array
            
        except Exception as e:
            print(f"❌ Error creating NumPy array: {e}")
            return None

    def test_server_connection(self):
        """Test if the FastAPI server is accessible"""
        return self._test_server_connectivity()

    def show(self):
        """Show the viewer"""
        if not HAS_IPYTHON:
            print("⚠️  Display not available without IPython")
            return
            
        print(f"🖥️  Displaying 3DMol viewer (ID: {self.id})...")
        html = self.startjs()
        ipyd.display(ipyd.HTML(html))
        
        # Execute all queued commands after viewer is created
        if self.commands:
            print(f"📋 Executing {len(self.commands)} queued commands...")
            self._execute_queued_commands()
        
        print("✅ Viewer displayed and commands executed")

    def startjs(self):
        """Get the starting JavaScript HTML"""
        html = f"""
        <div id="{self.id}" style="height: {self.height}px; width: {self.width}px; position: relative; border: 1px solid #ccc; background-color: #f9f9f9;">
            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #666;">
                Loading 3DMol viewer...
            </div>
        </div>
        <script>
        (function() {{
            console.log('🔧 Initializing 3DMol viewer for: {self.id}');
            
            // Global variables for this viewer
            window.py3dmol_viewer_ready = window.py3dmol_viewer_ready || {{}};
            window.py3dmol_loading_status = window.py3dmol_loading_status || {{}};
            
            // Function to load scripts with better error handling
            function loadScript(src, callback, errorCallback) {{
                console.log('📥 Loading script:', src);
                var script = document.createElement('script');
                script.src = src;
                script.async = true;
                script.crossOrigin = 'anonymous';
                
                var timeoutId = setTimeout(function() {{
                    console.error('❌ Script loading timeout:', src);
                    if (errorCallback) errorCallback();
                }}, 10000); // 10 second timeout
                
                script.onload = function() {{
                    clearTimeout(timeoutId);
                    console.log('✅ Script loaded successfully:', src);
                    if (callback) callback();
                }};
                
                script.onerror = function(e) {{
                    clearTimeout(timeoutId);
                    console.error('❌ Failed to load script:', src, e);
                    if (errorCallback) errorCallback();
                }};
                
                document.head.appendChild(script);
            }}
            
            // Function to check if element exists and is visible
            function isElementReady(elementId) {{
                var element = document.getElementById(elementId);
                if (!element) {{
                    console.log('❌ Element not found:', elementId);
                    return false;
                }}
                var rect = element.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) {{
                    console.log('❌ Element has zero size:', elementId, rect);
                    return false;
                }}
                console.log('✅ Element ready:', elementId, rect);
                return true;
            }}
            
            // Function to initialize 3DMol viewer
            function init3DMolViewer() {{
                console.log('🎯 Attempting to initialize 3DMol viewer...');
                
                // Check dependencies
                if (typeof $ === 'undefined') {{
                    console.error('❌ jQuery not available');
                    return false;
                }}
                if (typeof $3Dmol === 'undefined') {{
                    console.error('❌ 3Dmol.js not available');
                    return false;
                }}
                
                // Check if element is ready
                if (!isElementReady('{self.id}')) {{
                    console.log('⏳ Element not ready, retrying in 100ms...');
                    setTimeout(init3DMolViewer, 100);
                    return false;
                }}
                
                try {{
                    console.log('🔧 Creating 3DMol viewer...');
                    console.log('🔍 Available globals: $3Dmol=', typeof $3Dmol, ', $=', typeof $);
                    
                    // Debug 3DMol availability
                    if (typeof $3Dmol === 'undefined') {{
                        console.error('❌ $3Dmol is not defined!');
                        document.getElementById('{self.id}').innerHTML = 
                            '<div style="color: red; text-align: center; padding: 20px;">3DMol.js not loaded</div>';
                        return false;
                    }}
                    
                    console.log('🔍 $3Dmol methods:', Object.getOwnPropertyNames($3Dmol));
                    
                    // Initialize viewers object (following 3Dmol.js documentation pattern)
                    $3Dmol.viewers = $3Dmol.viewers || {{}};
                    
                    // Get the element using native DOM method first, then jQuery
                    var element = document.getElementById('{self.id}');
                    if (!element) {{
                        console.error('❌ Could not find element: {self.id}');
                        return false;
                    }}
                    
                    console.log('✅ Found element:', element);
                    console.log('📊 Element dimensions:', element.offsetWidth, 'x', element.offsetHeight);
                    
                    // Clear any loading message
                    element.innerHTML = '';
                    
                    // Create the viewer with minimal configuration first
                    var config = {{
                        backgroundColor: 'white'
                    }};
                    
                    console.log('📊 Creating viewer with config:', config);
                    console.log('🔍 Calling $3Dmol.createViewer...');
                    
                    var viewer = $3Dmol.createViewer(element, config);
                    
                    console.log('📊 createViewer returned:', viewer);
                    console.log('📊 Viewer type:', typeof viewer);
                    
                    if (!viewer) {{
                        console.error('❌ $3Dmol.createViewer returned null/undefined');
                        document.getElementById('{self.id}').innerHTML = 
                            '<div style="color: red; text-align: center; padding: 20px;">Failed to create 3DMol viewer</div>';
                        return false;
                    }}
                    
                    // Store the viewer in the global viewers object
                    $3Dmol.viewers['{self.id}'] = viewer;
                    
                    // Set viewer ready flag
                    window.py3dmol_viewer_ready['{self.id}'] = true;
                    
                    console.log('✅ 3DMol viewer created successfully:', '{self.id}');
                    console.log('📊 Viewer methods:', Object.getOwnPropertyNames(viewer).slice(0, 10));
                    
                    // Initialize the viewer properly
                    try {{
                        viewer.render();
                        console.log('✅ Initial render completed');
                    }} catch (renderError) {{
                        console.warn('⚠️ Initial render failed:', renderError);
                    }}
                    
                    // Trigger any waiting command execution
                    if (window.py3dmol_execute_commands && window.py3dmol_execute_commands['{self.id}']) {{
                        console.log('🚀 Triggering queued command execution...');
                        window.py3dmol_execute_commands['{self.id}']();
                    }}
                    
                    return true;
                    
                }} catch (error) {{
                    console.error('❌ Error creating 3DMol viewer:', error);
                    console.error('❌ Stack trace:', error.stack);
                    console.error('❌ Error details:', error.message);
                    document.getElementById('{self.id}').innerHTML = 
                        '<div style="color: red; text-align: center; padding: 20px;">Error: ' + error.message + '</div>';
                    return false;
                }}
            }}
            
            // Function to load jQuery
            function loadJQuery(callback) {{
                if (typeof $ !== 'undefined') {{
                    console.log('✅ jQuery already available');
                    callback();
                    return;
                }}
                
                console.log('📥 Loading jQuery from CDN...');
                loadScript('https://code.jquery.com/jquery-3.6.0.min.js', 
                    function() {{
                        console.log('✅ jQuery loaded successfully');
                        // Verify jQuery is properly initialized
                        if (typeof $ !== 'undefined' && $.fn && $.fn.jquery) {{
                            console.log('✅ jQuery version:', $.fn.jquery);
                            setTimeout(callback, 100);
                        }} else {{
                            console.error('❌ jQuery loaded but not properly initialized');
                            document.getElementById('{self.id}').innerHTML = 
                                '<div style="color: red; text-align: center; padding: 20px;">jQuery initialization failed</div>';
                        }}
                    }},
                    function() {{
                        console.error('❌ Failed to load jQuery from CDN');
                        document.getElementById('{self.id}').innerHTML = 
                            '<div style="color: red; text-align: center; padding: 20px;">Failed to load jQuery</div>';
                    }}
                );
            }}
            
            // Function to load 3Dmol.js
            function load3DMol(callback) {{
                if (typeof $3Dmol !== 'undefined') {{
                    console.log('✅ 3Dmol.js already available');
                    callback();
                    return;
                }}
                
                // Try multiple CDN sources for better reliability
                var cdnSources = [
                    'https://3Dmol.org/build/3Dmol-min.js',
                    'https://cdn.jsdelivr.net/npm/3dmol@latest/build/3Dmol-min.js',
                    'https://unpkg.com/3dmol@latest/build/3Dmol-min.js'
                ];
                
                var currentCdnIndex = 0;
                
                function tryNextCDN() {{
                    if (currentCdnIndex >= cdnSources.length) {{
                        console.error('❌ All CDN sources failed');
                        console.error('❌ Tried sources:', cdnSources);
                        document.getElementById('{self.id}').innerHTML = 
                            '<div style="color: red; text-align: center; padding: 20px;">Failed to load 3Dmol.js from all CDN sources</div>';
                        return;
                    }}
                    
                    var cdnUrl = cdnSources[currentCdnIndex];
                    console.log('📥 Loading 3Dmol.js from CDN (' + (currentCdnIndex + 1) + '/' + cdnSources.length + '):', cdnUrl);
                    
                    loadScript(cdnUrl,
                        function() {{
                            console.log('✅ 3Dmol.js loaded successfully from:', cdnUrl);
                            // Check if 3DMol is actually available
                            if (typeof $3Dmol !== 'undefined') {{
                                console.log('✅ $3Dmol is available, version info:', $3Dmol.version || 'unknown');
                                setTimeout(callback, 300);
                            }} else {{
                                console.error('❌ Script loaded but $3Dmol not available');
                                currentCdnIndex++;
                                setTimeout(tryNextCDN, 100);
                            }}
                        }},
                        function() {{
                            console.warn('⚠️ CDN failed:', cdnUrl);
                            currentCdnIndex++;
                            setTimeout(tryNextCDN, 100);
                        }}
                    );
                }}
                
                tryNextCDN();
            }}
            
            // Main initialization sequence
            function startInitialization() {{
                console.log('🚀 Starting 3DMol initialization sequence...');
                
                loadJQuery(function() {{
                    load3DMol(function() {{
                        // Wait for DOM to be fully ready
                        $(document).ready(function() {{
                            console.log('📄 DOM ready, initializing viewer...');
                            
                            // Try to initialize the viewer with retries
                            var maxRetries = 10;
                            var retryCount = 0;
                            
                            function tryInit() {{
                                if (init3DMolViewer()) {{
                                    console.log('🎉 3DMol viewer initialization complete!');
                                }} else {{
                                    retryCount++;
                                    if (retryCount < maxRetries) {{
                                        console.log(`⏳ Retry ${{retryCount}}/${{maxRetries}} in 200ms...`);
                                        setTimeout(tryInit, 200);
                                    }} else {{
                                        console.error('❌ Failed to initialize viewer after', maxRetries, 'attempts');
                                        document.getElementById('{self.id}').innerHTML = 
                                            '<div style="color: red; text-align: center; padding: 20px;">Failed to initialize 3DMol viewer</div>';
                                    }}
                                }}
                            }}
                            
                            tryInit();
                        }});
                    }});
                }});
            }}
            
            // Start the initialization
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', startInitialization);
            }} else {{
                startInitialization();
            }}
            
        }})();
        </script>
        """
        return html

    # Add common molecular viewer methods
    def addModel(self, data, format, options=None):
        """Add a molecular model to the viewer"""
        if options is None:
            options = {}
        
        # Use JSON encoding for the molecular data to avoid JavaScript syntax issues
        js_code = f"""
        var viewer = $3Dmol.viewers['{self.id}'];
        var moldata = {json.dumps(data)};
        var options = {json.dumps(options)};
        var model = viewer.addModel(moldata, "{format}", options);
        viewer.zoomTo();
        viewer.render();
        """
        self.executeCode(js_code)

    def setStyle(self, sel=None, style=None):
        """Set the style for molecular visualization"""
        if sel is None:
            sel = {}
        if style is None:
            style = {}
            
        js_code = f"""
        var viewer = $3Dmol.viewers['{self.id}'];
        viewer.setStyle({json.dumps(sel)}, {json.dumps(style)});
        viewer.render();
        """
        self.executeCode(js_code)

    def zoomTo(self, sel=None):
        """Zoom to fit the molecular structure"""
        if sel is None:
            sel = {}
            
        js_code = f"""
        var viewer = $3Dmol.viewers['{self.id}'];
        viewer.zoomTo({json.dumps(sel)});
        viewer.render();
        """
        self.executeCode(js_code)

    def render(self):
        """Render the viewer"""
        js_code = f"$3Dmol.viewers['{self.id}'].render();"
        self.executeCode(js_code)

    def rotate(self, angle, axis='y'):
        """Rotate the molecular view"""
        js_code = f"""
        var viewer = $3Dmol.viewers['{self.id}'];
        viewer.rotate({angle}, '{axis}');
        viewer.render();
        """
        self.executeCode(js_code)

    def setBackgroundColor(self, color):
        """Set the background color"""
        js_code = f"""
        var viewer = $3Dmol.viewers['{self.id}'];
        viewer.setBackgroundColor('{color}');
        viewer.render();
        """
        self.executeCode(js_code)

    def start_rotation(self, axis='y', speed=1):
        """Start continuous rotation of the molecular view"""
        js_code = f"""
        var viewer = $3Dmol.viewers['{self.id}'];
        
        // Stop any existing rotation
        if (window.py3dmol_rotation_interval && window.py3dmol_rotation_interval['{self.id}']) {{
            clearInterval(window.py3dmol_rotation_interval['{self.id}']);
        }}
        
        // Initialize rotation intervals object
        window.py3dmol_rotation_interval = window.py3dmol_rotation_interval || {{}};
        
        // Start new rotation
        window.py3dmol_rotation_interval['{self.id}'] = setInterval(function() {{
            viewer.rotate({speed}, '{axis}');
            viewer.render();
        }}, 50); // Rotate every 50ms
        
        console.log('🔄 Started rotation on {axis} axis with speed {speed}');
        """
        self.executeCode(js_code)

    def stop_rotation(self):
        """Stop the continuous rotation"""
        js_code = f"""
        if (window.py3dmol_rotation_interval && window.py3dmol_rotation_interval['{self.id}']) {{
            clearInterval(window.py3dmol_rotation_interval['{self.id}']);
            window.py3dmol_rotation_interval['{self.id}'] = null;
            console.log('⏹️ Stopped rotation');
        }}
        """
        self.executeCode(js_code)


# Create EmptyViewer as an alias for JS3DMol for backward compatibility
class EmptyViewer(JS3DMol):
    """
    EmptyViewer class - alias for JS3DMol for backward compatibility
    """
    pass