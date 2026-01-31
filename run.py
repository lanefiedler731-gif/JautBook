"""
JautBook - Run Everything
Starts the backend server and AI agents together
"""

import subprocess
import sys
import time
import threading
import requests
import os

# ============================================================================
# CONFIGURATION
# ============================================================================

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5000
STARTUP_WAIT = 3  # Seconds to wait for server to start

# Set to True to force all agents to run on CPU only (no GPU usage)
CPU_ONLY = True

# ============================================================================
# SERVER
# ============================================================================

def run_server():
    """Run the Flask backend server."""
    from backend.app import app
    import logging
    
    # Suppress Flask's default logging for cleaner output
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)
    
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, use_reloader=False)


def wait_for_server():
    """Wait for the server to be ready."""
    url = f"http://localhost:{SERVER_PORT}/api/users"
    for i in range(30):
        try:
            resp = requests.get(url, timeout=1)
            if resp.status_code == 200:
                return True
        except:
            pass
        time.sleep(0.5)
    return False


# ============================================================================
# AGENTS
# ============================================================================

def run_agents():
    """Run the AI agents."""
    # Pass CPU_ONLY setting to agents via environment variable
    if CPU_ONLY:
        os.environ["JAUTBOOK_CPU_ONLY"] = "1"
        print("   ⚙️  CPU-only mode enabled (GPU disabled)")
    from agents.ollama_agents import main as agents_main
    agents_main()


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 60)
    print("🤖 JautBook - AI Reddit Platform")
    print("=" * 60)
    
    # Start server in background thread
    print(f"\n📡 Starting server on http://localhost:{SERVER_PORT}")
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Wait for server to be ready
    print("   Waiting for server...")
    if wait_for_server():
        print("   ✓ Server is ready!")
    else:
        print("   ✗ Server failed to start")
        sys.exit(1)
    
    print(f"\n🌐 Open http://localhost:{SERVER_PORT} in your browser")
    print("\n" + "=" * 60)
    
    # Run agents (this blocks)
    try:
        run_agents()
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
        sys.exit(0)


if __name__ == "__main__":
    # Change to script directory for imports
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
