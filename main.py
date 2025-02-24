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

def run_flask():
    """Run Flask in a separate thread"""
    try:
        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
    except Exception as e:
        logger.error(f"Failed to start Flask: {e}")
        raise

async def main():
    """Main async function to run both Flask and bot"""
    try:
        # Start Flask in a separate thread
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        logger.info("Flask admin interface started in background thread")

        # Initialize and run bot in main thread
        logger.info("Starting Telegram bot...")
        bot = await init_bot()
        logger.info("Bot initialization completed")

        # Keep the main thread running
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise

if __name__ == "__main__":
    try:
        # Verify Telegram token
        if not os.environ.get("TELEGRAM_TOKEN"):
            raise ValueError("TELEGRAM_TOKEN environment variable is required")

        # Run the async main function
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application shutdown requested")
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise