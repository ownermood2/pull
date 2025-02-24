import os
import sys
import time
import signal
import logging
import subprocess
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('supervisor.log')
    ]
)
logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Handle termination signals gracefully"""
    logger.info(f"Received signal {signum}")
    sys.exit(0)

def run_bot_forever():
    """Keep the bot running forever with automatic restarts"""
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    restart_count = 0
    last_start_time = None

    while True:
        try:
            current_time = datetime.now()
            
            # If the bot has been restarting too frequently, wait longer
            if last_start_time and (current_time - last_start_time).seconds < 60:
                restart_count += 1
                wait_time = min(30 * restart_count, 300)  # Max 5 minutes wait
                logger.warning(f"Bot restarting too frequently. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                restart_count = 0
            
            last_start_time = current_time
            logger.info("Starting bot process...")
            
            # Start the main bot process
            process = subprocess.Popen([sys.executable, 'main.py'])
            
            # Wait for the process to finish
            process.wait()
            
            # If the process exited with an error
            if process.returncode != 0:
                logger.error(f"Bot process exited with code {process.returncode}")
            else:
                logger.info("Bot process finished normally")
            
            # Small delay before restart
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"Error in supervisor: {str(e)}")
            time.sleep(5)
            continue

if __name__ == "__main__":
    try:
        logger.info("Starting bot supervisor...")
        run_bot_forever()
    except KeyboardInterrupt:
        logger.info("Supervisor shutdown requested")
    except Exception as e:
        logger.error(f"Fatal supervisor error: {str(e)}")
        sys.exit(1)
