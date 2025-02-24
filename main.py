import os
import logging
import asyncio
from flask import Flask
from app import app, init_bot
import threading
import signal

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flag to control the application lifecycle
is_running = True

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global is_running
    logger.info(f"Received signal {signum}")
    is_running = False

def run_flask():
    """Run Flask in a separate thread"""
    try:
        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
    except Exception as e:
        logger.error(f"Failed to start Flask: {e}")
        raise

if __name__ == "__main__":
    try:
        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Verify Telegram token
        if not os.environ.get("TELEGRAM_TOKEN"):
            raise ValueError("TELEGRAM_TOKEN environment variable is required")

        # Start Flask in a background thread
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        logger.info("Flask admin interface started in background thread")

        # Run Telegram bot in the main thread
        logger.info("Starting Telegram bot in main thread...")
        asyncio.run(init_bot())

    except KeyboardInterrupt:
        logger.info("Application shutdown requested")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise