import os
import sys
import time
import signal
import logging
import subprocess
from datetime import datetime, timedelta
import psutil

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

def check_process_memory(pid):
    """Monitor process memory usage"""
    try:
        process = psutil.Process(pid)
        memory_usage = process.memory_info().rss / 1024 / 1024  # Convert to MB
        return memory_usage
    except Exception as e:
        logger.error(f"Error checking memory usage: {e}")
        return 0

def signal_handler(signum, frame):
    """Handle termination signals gracefully"""
    logger.info(f"Received signal {signum}")
    sys.exit(0)

def run_bot_forever():
    """Keep the bot running forever with automatic restarts and monitoring"""
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    restart_count = 0
    last_start_time = None
    memory_threshold = 500  # MB

    while True:
        try:
            current_time = datetime.now()

            # If the bot has been restarting too frequently, implement exponential backoff
            if last_start_time and (current_time - last_start_time).seconds < 60:
                restart_count += 1
                wait_time = min(30 * (2 ** restart_count), 300)  # Max 5 minutes wait
                logger.warning(f"Bot restarting too frequently. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                restart_count = 0

            last_start_time = current_time
            logger.info("Starting bot process...")

            # Start the main bot process
            process = subprocess.Popen(
                [sys.executable, 'main.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            # Monitor the process
            while process.poll() is None:
                # Check memory usage
                memory_usage = check_process_memory(process.pid)
                if memory_usage > memory_threshold:
                    logger.warning(f"Memory usage too high ({memory_usage}MB). Restarting...")
                    process.terminate()
                    break

                # Read output for logging
                stdout = process.stdout.readline()
                if stdout:
                    logger.info(stdout.strip())
                stderr = process.stderr.readline()
                if stderr:
                    logger.error(stderr.strip())

                time.sleep(1)

            # If the process exited
            if process.returncode is not None:
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