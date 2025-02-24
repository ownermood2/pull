import os
import sys
import logging
import asyncio
import signal
import threading
import traceback
from datetime import datetime, timedelta
from flask import Flask
from app import app, init_bot
from keep_alive import start_keep_alive

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Global variables for tracking
last_restart = datetime.now()
error_count = 0
MAX_ERRORS = 5  # Reduced from 10 to be more proactive
RESTART_INTERVAL = timedelta(hours=12)  # Reduced from 24 to 12 hours for more frequent refreshes

def run_flask():
    """Run Flask in a separate thread"""
    try:
        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
    except Exception as e:
        logger.error(f"Failed to start Flask: {e}")
        raise

def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.error("Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))

def signal_handler(signum, frame):
    """Handle termination signals"""
    logger.info(f"Received signal {signum}")
    raise SystemExit("Received termination signal")

async def health_check():
    """Perform regular health checks"""
    while True:
        try:
            # Check memory usage
            import psutil
            process = psutil.Process(os.getpid())
            memory_usage = process.memory_info().rss / 1024 / 1024  # MB

            if memory_usage > 500:  # 500MB threshold
                logger.warning(f"High memory usage detected: {memory_usage}MB")
                os.execv(sys.executable, ['python'] + sys.argv)

            await asyncio.sleep(300)  # Check every 5 minutes
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            await asyncio.sleep(60)  # Wait a minute before retrying

async def scheduled_restart():
    """Perform scheduled restarts"""
    while True:
        try:
            await asyncio.sleep(RESTART_INTERVAL.total_seconds())
            logger.info("Performing scheduled restart")
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            logger.error(f"Error in scheduled restart: {e}")

async def main():
    """Main async function to run both Flask and bot"""
    global error_count, last_restart

    try:
        # Set up signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # Start keep-alive server first
        start_keep_alive()
        logger.info("Keep-alive server started")

        # Start Flask in a separate thread
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        logger.info("Flask admin interface started in background thread")

        # Initialize and run bot in main thread
        logger.info("Starting Telegram bot...")
        bot = await init_bot()
        logger.info("Bot initialization completed")

        # Start scheduled restart and health check tasks
        asyncio.create_task(scheduled_restart())
        asyncio.create_task(health_check())

        # Reset error count after successful start
        error_count = 0
        last_restart = datetime.now()

        # Keep the main thread running
        while True:
            try:
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                error_count += 1

                if error_count >= MAX_ERRORS:
                    logger.critical("Too many errors, performing emergency restart")
                    os.execv(sys.executable, ['python'] + sys.argv)

                continue

    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Critical error: {e}\n{traceback.format_exc()}")
        await asyncio.sleep(5)
        os.execv(sys.executable, ['python'] + sys.argv)

if __name__ == "__main__":
    try:
        # Set up global exception handler
        sys.excepthook = handle_exception

        # Verify environment variables
        required_vars = ["TELEGRAM_TOKEN", "SESSION_SECRET"]
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

        # Run the async main function
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application shutdown requested")
    except Exception as e:
        logger.critical(f"Fatal error: {e}\n{traceback.format_exc()}")
        sys.exit(1)