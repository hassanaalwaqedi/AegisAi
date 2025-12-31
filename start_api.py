#!/usr/bin/env python3
"""
AegisAI API Server Start Script

Suppresses numpy warnings before any imports to prevent Python 3.14 crashes.
"""

# === WARNING SUPPRESSION (MUST BE FIRST) ===
import warnings
import os
import sys

# Suppress ALL warnings before any imports
warnings.filterwarnings('ignore')
warnings.filterwarnings('ignore', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=UserWarning)
os.environ['PYTHONWARNINGS'] = 'ignore'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Suppress numpy warnings specifically
import numpy as np
np.seterr(all='ignore')
# === END WARNING SUPPRESSION ===

# Now start uvicorn
if __name__ == "__main__":
    import uvicorn
    from aegis.api.app import create_app
    
    app = create_app()
    
    host = os.getenv("AEGIS_API_HOST", "127.0.0.1")
    port = int(os.getenv("AEGIS_API_PORT", "8080"))
    debug = os.getenv("AEGIS_DEBUG", "false").lower() == "true"
    
    print(f"Starting AegisAI API on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, reload=debug)

