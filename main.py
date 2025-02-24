import os
import logging
import asyncio
from flask import Flask
from app import app, init_bot
import threading

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def start_telegram_bot():
    """Run Telegram bot in a separate thread"""
    try:
        # Verify token
        if not os.environ.get("TELEGRAM_TOKEN"):
            logger.error("TELEGRAM_TOKEN environment variable is not set")
            raise ValueError("TELEGRAM_TOKEN environment variable is required")

        # Run the bot
        asyncio.run(init_bot())
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}")
        raise

def main():
    """Entry point of the application"""
    try:
        # Start Telegram bot in a separate thread
        bot_thread = threading.Thread(target=start_telegram_bot)
        bot_thread.daemon = True  # Allow the thread to be terminated when main program exits
        bot_thread.start()
        logger.info("Telegram bot thread started")

        # Run Flask in the main thread
        logger.info("Starting Flask admin interface")
        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)

    except KeyboardInterrupt:
        logger.info("Application shutdown requested")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise

if __name__ == "__main__":
    main()