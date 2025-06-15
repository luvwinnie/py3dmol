try:
    from py3dmol.highlevel import *
    from py3dmol.interfaces import *
    
    # Start the image server when py3dmol is imported
    from py3dmol.image_server import start_server
    try:
        _image_server = start_server()
        print("🚀 Py3DMol HTTP server started on port 8769")
    except Exception as e:
        print(f"⚠️  Warning: Could not start image server: {e}")
        _image_server = None
        
except ImportError as e:
    print(f"Error importing py3dmol modules: {e}")
    raise