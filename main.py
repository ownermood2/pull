import os
import logging
import asyncio
from flask import Flask
from app import app, init_bot
from quiz_manager import QuizManager
import threading

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def start_flask():
    """Start the Flask admin interface"""
    try:
        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
    except Exception as e:
        logger.error(f"Failed to start Flask: {e}")
        raise

async def async_main():
    """Main async function to run both Flask and Telegram bot"""
    # Check for required environment variables
    if not os.environ.get("TELEGRAM_TOKEN"):
        logger.error("TELEGRAM_TOKEN environment variable is not set")
        raise ValueError("TELEGRAM_TOKEN environment variable is required")

    try:
        # Start Flask in a separate thread
        flask_thread = threading.Thread(target=start_flask)
        flask_thread.daemon = True
        flask_thread.start()
        logger.info("Flask admin interface started in background thread")

        # Initialize bot handlers and start the bot
        logger.info("Starting Telegram bot...")
        await init_bot()

        # Keep the main thread running
        while True:
            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Application startup failed: {e}")
        raise

def main():
    """Entry point of the application"""
    try:
        # Run the async main function
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Application shutdown requested")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise

if __name__ == "__main__":
    main()
