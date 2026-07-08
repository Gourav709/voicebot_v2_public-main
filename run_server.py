"""
Web server mode — run this instead of run_local_v2.py for browser access.

Usage:
  1. python run_server.py
  2. In another terminal: ngrok http 8000
  3. Share the ngrok HTTPS URL with your team
"""
import uvicorn
from src.app.server import app

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  DSP Voice Bot — Web Server Mode")
    print("="*55)
    print("  Local:  http://localhost:8000")
    print("  Expose: ngrok http 8000")
    print("="*55 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")