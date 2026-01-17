#!/usr/bin/env python3
"""
Chimera Core - The Body (Python Worker)

Python 3.12 worker service that connects to The Brain via gRPC.
This is a minimal entry point to pass Railway healthchecks.
# Cache invalidation: 2026-01-17 - Force Railway rebuild
"""

import os
import sys
import logging
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for Railway healthchecks"""
    
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"healthy","service":"chimera-core"}')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP server logs
        pass


def start_health_server(port: int = 8080):
    """Start HTTP healthcheck server, binding to 0.0.0.0 for Railway"""
    def run_server():
        server_address = ('0.0.0.0', port)
        server = HTTPServer(server_address, HealthCheckHandler)
        logger.info(f"🏥 Health check server started on 0.0.0.0:{port}")
        server.serve_forever()
    
    thread = Thread(target=run_server, daemon=True)
    thread.start()
    return thread


def main():
    """Main entry point for Chimera Core worker"""
    logger.info("🦾 Chimera Core - The Body - Starting...")
    logger.info("   Version: Python 3.12")
    
    # Get environment variables
    health_port = int(os.getenv("PORT", "8080"))
    brain_address = os.getenv("CHIMERA_BRAIN_ADDRESS", "http://chimera-brain.railway.internal:50051")
    railway_env = os.getenv("RAILWAY_ENVIRONMENT", "development")
    
    logger.info(f"   Environment: {railway_env}")
    logger.info(f"   Brain Address: {brain_address}")
    
    # Start health check server (Railway requirement)
    start_health_server(health_port)
    
    # TODO: Initialize gRPC client to connect to The Brain
    # TODO: Implement worker swarm logic
    # For now, just keep the service alive
    
    logger.info("✅ Chimera Core worker started")
    logger.info("   - Health Server: Active")
    logger.info("   - Brain Connection: Pending implementation")
    logger.info("   - Worker Status: Ready")
    
    try:
        # Keep the service alive
        while True:
            time.sleep(60)
            logger.debug("Worker heartbeat...")
    except KeyboardInterrupt:
        logger.info("Shutting down Chimera Core worker")
        sys.exit(0)


if __name__ == "__main__":
    main()
