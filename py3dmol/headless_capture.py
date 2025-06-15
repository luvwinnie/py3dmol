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

# Global driver cache for faster subsequent captures
_global_driver_cache = None

class HeadlessCapture:
    """Headless image capture using Selenium WebDriver"""
    
    def __init__(self, reuse_driver=True):
        self.driver = None
        self.reuse_driver = reuse_driver
        self._setup_driver()
    
    def _setup_driver(self):
        """Setup headless Chrome/Firefox driver"""
        global _global_driver_cache
        
        # Try to reuse existing driver if available
        if self.reuse_driver and _global_driver_cache is not None:
            try:
                # Test if driver is still working
                _global_driver_cache.current_url
                self.driver = _global_driver_cache
                print("✅ Reusing existing headless driver (faster!)")
                return
            except:
                # Driver is dead, create new one
                _global_driver_cache = None
        
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
                    _global_driver_cache = self.driver
                    print("✅ Headless Chrome driver initialized")
                    return
                except ImportError:
                    # Try system chromedriver
                    self.driver = webdriver.Chrome(options=options)
                    _global_driver_cache = self.driver
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
                    _global_driver_cache = self.driver
                    print("✅ Headless Firefox driver initialized")
                    return
                except ImportError:
                    self.driver = webdriver.Firefox(options=options)
                    _global_driver_cache = self.driver
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
                
                # Smart wait for 3DMol to load and render (with polling instead of fixed sleep)
                max_wait_time = 8  # Maximum 8 seconds
                poll_interval = 0.2  # Check every 200ms
                start_time = time.time()
                
                # Fast polling for viewer readiness
                while time.time() - start_time < max_wait_time:
                    try:
                        ready_result = self.driver.execute_script("""
                            if (typeof $3Dmol === 'undefined') {
                                return {status: 'loading', message: '$3Dmol loading...'};
                            }
                            
                            if (!window.viewer) {
                                return {status: 'loading', message: 'viewer loading...'};
                            }
                            
                            // Force render and check if canvas is ready
                            window.viewer.render();
                            var canvas = window.viewer.getCanvas();
                            
                            if (!canvas || canvas.width === 0 || canvas.height === 0) {
                                return {status: 'loading', message: 'canvas loading...'};
                            }
                            
                            return {status: 'success', message: 'Viewer ready'};
                        """)
                        
                        if ready_result and ready_result.get('status') == 'success':
                            elapsed = time.time() - start_time
                            print(f"🔍 Viewer readiness check: {ready_result} (took {elapsed:.1f}s)")
                            break
                            
                    except Exception as e:
                        # Continue polling if JavaScript not ready yet
                        pass
                    
                    time.sleep(poll_interval)
                else:
                    # Timeout reached
                    print(f"⚠️ Viewer ready timeout after {max_wait_time}s - proceeding anyway")
                    
                    # Check for JavaScript errors only on timeout
                    try:
                        logs = self.driver.get_log('browser')
                        if logs:
                            print("🔍 Browser console logs:")
                            for log in logs[-3:]:  # Show last 3 logs only
                                if log['level'] in ['SEVERE', 'ERROR']:
                                    print(f"   {log['level']}: {log['message']}")
                    except:
                        pass
                
                # Fast canvas capture with minimal logging
                canvas_data = self.driver.execute_script("""
                    if (!window.viewer) return null;
                    
                    try {
                        var canvas = window.viewer.getCanvas();
                        if (!canvas || canvas.width === 0 || canvas.height === 0) return null;
                        return canvas.toDataURL('image/""" + format + """');
                    } catch (error) {
                        return null;
                    }
                """)
                
                if canvas_data:
                    print(f"✅ Headless capture successful")
                    return canvas_data
                else:
                    print("❌ Canvas capture failed")
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
        
        # Fast command extraction - simplified logic
        viewer_commands = []
        
        if hasattr(viewer, 'commands') and viewer.commands:
            print(f"🔍 Extracting {len(viewer.commands)} commands...")
            
            for cmd in viewer.commands:
                # Simple extraction - just use the command as-is since we're queueing them now
                if cmd and cmd.strip():
                    viewer_commands.append(cmd.strip())
        
        # If no commands found, create a basic empty viewer
        if not viewer_commands:
            viewer_commands = ["console.log('Empty viewer created');"]
        
        print(f"✅ Using {len(viewer_commands)} commands")
        
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