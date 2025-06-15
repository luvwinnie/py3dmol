"""
Headless Image Capture for Py3DMol
==================================

This module provides headless image capture functionality for py3dmol
when running outside of Jupyter notebooks (e.g., in scripts, servers, etc.).

Uses Selenium WebDriver with headless browser to render and capture images.
"""

import os
import time
import tempfile
import base64
from typing import Optional, Tuple
import logging

# Set up logging
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

class HeadlessCapture:
    """Headless image capture using Selenium WebDriver"""
    
    def __init__(self):
        self.driver = None
        self._setup_driver()
    
    def _setup_driver(self):
        """Setup headless Chrome/Firefox driver"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.chrome.service import Service as ChromeService
            
            # Try Chrome first
            try:
                options = ChromeOptions()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--window-size=1920,1080')
                options.add_argument('--disable-web-security')
                options.add_argument('--allow-running-insecure-content')
                
                # WebGL support flags (don't disable GPU for WebGL)
                options.add_argument('--enable-webgl')
                options.add_argument('--use-gl=swiftshader')  # Software rendering for WebGL
                options.add_argument('--enable-accelerated-2d-canvas')
                options.add_argument('--disable-gpu-sandbox')
                options.add_argument('--ignore-gpu-blacklist')
                options.add_argument('--enable-unsafe-swiftshader')
                options.add_argument('--disable-features=VizDisplayCompositor')
                
                # Try to find Chrome driver automatically
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    service = ChromeService(ChromeDriverManager().install())
                    self.driver = webdriver.Chrome(service=service, options=options)
                    print("✅ Headless Chrome driver initialized")
                    return
                except ImportError:
                    # Try system chromedriver
                    self.driver = webdriver.Chrome(options=options)
                    print("✅ Headless Chrome driver initialized (system)")
                    return
                    
            except Exception as e:
                print(f"❌ Chrome driver failed: {e}")
                
            # Try Firefox as fallback
            try:
                from selenium.webdriver.firefox.options import Options as FirefoxOptions
                from selenium.webdriver.firefox.service import Service as FirefoxService
                
                options = FirefoxOptions()
                options.add_argument('--headless')
                options.add_argument('--width=1920')
                options.add_argument('--height=1080')
                
                try:
                    from webdriver_manager.firefox import GeckoDriverManager
                    service = FirefoxService(GeckoDriverManager().install())
                    self.driver = webdriver.Firefox(service=service, options=options)
                    print("✅ Headless Firefox driver initialized")
                    return
                except ImportError:
                    self.driver = webdriver.Firefox(options=options)
                    print("✅ Headless Firefox driver initialized (system)")
                    return
                    
            except Exception as e:
                print(f"❌ Firefox driver failed: {e}")
                
        except ImportError:
            print("❌ Selenium not available. Install with: pip install selenium webdriver-manager")
            
        self.driver = None
    
    def is_available(self) -> bool:
        """Check if headless capture is available"""
        return self.driver is not None
    
    def capture_viewer_image(self, viewer, width: int = 800, height: int = 600, 
                           format: str = 'png') -> Optional[str]:
        """
        Capture image from py3dmol viewer in headless mode
        
        Args:
            viewer: py3dmol viewer object
            width: Image width
            height: Image height
            format: Image format ('png' or 'jpeg')
            
        Returns:
            Base64 encoded image data or None if failed
        """
        if not self.is_available():
            print("❌ Headless capture not available")
            return None
            
        try:
            # Create a temporary HTML file with the viewer
            html_content = self._create_viewer_html(viewer, width, height)
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html_content)
                html_file = f.name
            
            try:
                # Load the HTML file in headless browser
                self.driver.get(f"file://{html_file}")
                
                # Wait for 3DMol to load and render
                time.sleep(3)
                
                # Check if page loaded properly
                page_title = self.driver.title
                print(f"📄 Page title: {page_title}")
                
                # Check for JavaScript errors
                logs = self.driver.get_log('browser')
                if logs:
                    print("🔍 Browser console logs:")
                    for log in logs[-5:]:  # Show last 5 logs
                        print(f"   {log['level']}: {log['message']}")
                
                # Wait for viewer to be ready
                ready_result = self.driver.execute_script("""
                    console.log('🔍 Checking viewer readiness...');
                    
                    if (typeof $3Dmol === 'undefined') {
                        console.log('❌ $3Dmol not loaded');
                        return {status: 'error', message: '$3Dmol not loaded'};
                    }
                    
                    if (!window.viewer) {
                        console.log('❌ window.viewer not found');
                        return {status: 'error', message: 'window.viewer not found'};
                    }
                    
                    console.log('✅ Viewer found, rendering...');
                    window.viewer.render();
                    
                    return {status: 'success', message: 'Viewer ready'};
                """)
                
                print(f"🔍 Viewer readiness check: {ready_result}")
                
                # Wait a bit more for rendering
                time.sleep(2)
                
                # Capture canvas as base64
                canvas_data = self.driver.execute_script("""
                    console.log('🎨 Attempting canvas capture...');
                    
                    if (!window.viewer) {
                        console.log('❌ No viewer found');
                        return null;
                    }
                    
                    try {
                        var canvas = window.viewer.getCanvas();
                        console.log('📷 Canvas:', canvas);
                        
                        if (!canvas) {
                            console.log('❌ No canvas returned from viewer');
                            return null;
                        }
                        
                        console.log('📐 Canvas size:', canvas.width, 'x', canvas.height);
                        
                        if (canvas.width === 0 || canvas.height === 0) {
                            console.log('❌ Canvas has zero size');
                            return null;
                        }
                        
                        var dataURL = canvas.toDataURL('image/""" + format + """');
                        console.log('✅ Canvas captured, data length:', dataURL.length);
                        
                        return dataURL;
                        
                    } catch (error) {
                        console.log('❌ Error capturing canvas:', error);
                        return null;
                    }
                """)
                
                print(f"🎨 Canvas capture result: {canvas_data is not None}")
                if canvas_data:
                    print(f"   📏 Data length: {len(canvas_data)}")
                
                if canvas_data:
                    print(f"✅ Headless image capture successful")
                    return canvas_data
                else:
                    print("❌ No canvas data captured")
                    
                    # Get final browser logs
                    final_logs = self.driver.get_log('browser')
                    if final_logs:
                        print("🔍 Final browser logs:")
                        for log in final_logs[-3:]:
                            print(f"   {log['level']}: {log['message']}")
                    
                    return None
                    
            finally:
                # Clean up temp file
                try:
                    os.unlink(html_file)
                except:
                    pass
                    
        except Exception as e:
            print(f"❌ Headless capture error: {e}")
            return None
    
    def _create_viewer_html(self, viewer, width: int, height: int) -> str:
        """Create standalone HTML file with 3DMol viewer"""
        
        # Extract the actual commands that were sent to the viewer
        # This will replay the same molecular data and styling
        viewer_commands = []
        
        print(f"🔍 Extracting commands from viewer (has {len(getattr(viewer, 'commands', []))} commands)")
        
        # Get the commands from the viewer object
        if hasattr(viewer, 'commands') and viewer.commands:
            # Extract the actual JavaScript commands
            for i, cmd in enumerate(viewer.commands):
                print(f"  📝 Command {i+1}: {cmd[:100]}...")
                
                # Clean up the command by extracting the core JavaScript
                if 'executeWhenReady' in cmd:
                    # Extract the inner JavaScript from the wrapper
                    try_start = cmd.find('try {')
                    if try_start != -1:
                        # Find the matching closing brace for the try block
                        brace_count = 0
                        start_pos = try_start + 5  # After 'try {'
                        
                        for j, char in enumerate(cmd[start_pos:], start_pos):
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                if brace_count == 0:
                                    # This is the closing brace for the try block
                                    inner_js = cmd[start_pos:j].strip()
                                    if inner_js:
                                        viewer_commands.append(inner_js)
                                        print(f"    ✅ Extracted: {inner_js[:50]}...")
                                    break
                                else:
                                    brace_count -= 1
                else:
                    # Direct command
                    if cmd.strip():
                        viewer_commands.append(cmd.strip())
                        print(f"    ✅ Direct command: {cmd[:50]}...")
        
        # If no commands found, create a basic empty viewer
        if not viewer_commands:
            print("⚠️  No commands extracted - creating empty viewer")
            viewer_commands = [
                "console.log('⚠️  No molecular data found - creating empty viewer');"
            ]
        else:
            print(f"✅ Extracted {len(viewer_commands)} commands")
        
        # Join all commands
        commands_js = '\n        '.join(viewer_commands)
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <script src="https://3Dmol.csb.pitt.edu/build/3Dmol-min.js"></script>
    <style>
        body {{ margin: 0; padding: 0; background: white; }}
        #viewer {{ width: {width}px; height: {height}px; }}
    </style>
</head>
<body>
    <div id="viewer"></div>
    <script>
        console.log('🔧 Initializing headless 3DMol viewer');
        
        // Initialize 3DMol viewer
        var viewer = $3Dmol.createViewer("viewer", {{
            defaultcolors: $3Dmol.elementColors.Jmol,
            backgroundColor: 0xffffff
        }});
        
        // Store viewer globally for access
        window.viewer = viewer;
        
        // Create viewers object for compatibility with commands
        if (typeof $3Dmol !== 'undefined') {{
            $3Dmol.viewers = $3Dmol.viewers || {{}};
            $3Dmol.viewers['{viewer.id}'] = viewer;
            console.log('✅ Created viewer with ID: {viewer.id}');
        }}
        
        try {{
            console.log('🎬 Executing viewer commands...');
            
            // Execute the actual commands from the viewer
            {commands_js}
            
            // Ensure final render
            console.log('🎨 Final render...');
            viewer.render();
            
            console.log('✅ All commands executed successfully');
            
        }} catch (error) {{
            console.error('❌ Error executing viewer commands:', error);
            
            // Fallback: create a simple empty viewer
            console.log('🔄 Creating fallback empty viewer');
            viewer.render();
        }}
        
        // Mark as ready
        window.viewerReady = true;
        console.log('✅ Headless viewer ready');
    </script>
</body>
</html>
        """
        return html
    
    def close(self):
        """Close the webdriver"""
        if self.driver:
            try:
                self.driver.quit()
                print("✅ Headless driver closed")
            except:
                pass
            self.driver = None
    
    def __del__(self):
        """Cleanup on destruction"""
        self.close()


# Global instance
_headless_capture = None

def get_headless_capture() -> Optional[HeadlessCapture]:
    """Get global headless capture instance"""
    global _headless_capture
    if _headless_capture is None:
        _headless_capture = HeadlessCapture()
    return _headless_capture

def capture_headless_image(viewer, width: int = 800, height: int = 600, 
                          format: str = 'png') -> Optional[str]:
    """
    Convenience function to capture image in headless mode
    
    Args:
        viewer: py3dmol viewer object
        width: Image width
        height: Image height
        format: Image format ('png' or 'jpeg')
        
    Returns:
        Base64 encoded image data or None if failed
    """
    capture = get_headless_capture()
    if capture and capture.is_available():
        return capture.capture_viewer_image(viewer, width, height, format)
    return None

def is_headless_available() -> bool:
    """Check if headless capture is available"""
    capture = get_headless_capture()
    return capture is not None and capture.is_available() 