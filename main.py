import os
import logging
import asyncio
from flask import Flask
from app import app, init_bot
import threading
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_flask():
    """Run Flask in a separate thread"""
    try:
        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False, threaded=True)
    except Exception as e:
        logger.error(f"Failed to start Flask: {e}")
        raise

def run_bot_forever():
    """Run the Telegram bot in a separate thread with its own event loop"""
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the bot
        loop.run_until_complete(init_bot())
        loop.run_forever()
    except Exception as e:
        logger.error(f"Bot thread error: {e}")
        raise
    finally:
        loop.close()

def main():
    """Entry point of the application"""
    try:
        # Start Flask in a thread
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        logger.info("Flask admin interface started in background thread")

        # Start bot in another thread
        bot_thread = threading.Thread(target=run_bot_forever)
        bot_thread.daemon = True
        bot_thread.start()
        logger.info("Telegram bot thread started")

        # Keep main thread alive
        while True:
            try:
                flask_thread.join(1)
                bot_thread.join(1)
            except KeyboardInterrupt:
                logger.info("Shutdown requested")
                break

    except Exception as e:
        logger.error(f"Application error: {e}")
        raise

if __name__ == "__main__":
    main()