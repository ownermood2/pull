import os
import logging
import threading
import time
import psutil
import requests
from flask import Flask, jsonify
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
keep_alive_app = Flask('')
start_time = datetime.now()

@keep_alive_app.route('/')
def home():
    """Main endpoint for UptimeRobot to ping"""
    return "Bot is alive!"

@keep_alive_app.route('/health')
def health():
    """Health check endpoint with detailed status"""
    uptime = datetime.now() - start_time
    process = psutil.Process(os.getpid())
    memory_usage = process.memory_info().rss / 1024 / 1024  # Convert to MB

    return jsonify({
        'status': 'alive',
        'uptime': str(uptime),
        'memory_usage_mb': round(memory_usage, 2),
        'timestamp': datetime.now().isoformat()
    })

def run():
    """Run Flask server"""
    # Using port 5000 as required by Replit
    keep_alive_app.run(host='0.0.0.0', port=5000)

def ping_server():
    """Ping server every minute to keep it alive"""
    consecutive_failures = 0
    max_failures = 3
    while True:
        try:
            # Try both endpoints for redundancy
            response1 = requests.get(
                f"https://{os.environ['REPL_SLUG']}.{os.environ['REPL_OWNER']}.repl.co/",
                timeout=30
            )
            response2 = requests.get(
                f"https://{os.environ['REPL_SLUG']}.{os.environ['REPL_OWNER']}.repl.co/health",
                timeout=30
            )

            if response1.status_code == 200 and response2.status_code == 200:
                logger.info("Server pinged successfully")
                consecutive_failures = 0
            else:
                raise Exception(f"Unexpected status codes: / ({response1.status_code}), /health ({response2.status_code})")
        except Exception as e:
            consecutive_failures += 1
            logger.error(f"Failed to ping server (attempt {consecutive_failures}): {e}")

            if consecutive_failures >= max_failures:
                logger.critical("Multiple ping failures detected, restarting application...")
                os._exit(1)  # Force restart through process manager

        time.sleep(60)  # Check every minute

def monitor_memory():
    """Monitor and manage memory usage"""
    memory_threshold = 500  # MB
    consecutive_high_memory = 0
    max_high_memory = 3

    while True:
        try:
            process = psutil.Process(os.getpid())
            memory_usage = process.memory_info().rss / 1024 / 1024  # Convert to MB

            if memory_usage > memory_threshold:
                consecutive_high_memory += 1
                logger.warning(f"High memory usage detected: {memory_usage}MB (occurrence {consecutive_high_memory})")

                # Trigger garbage collection
                import gc
                gc.collect()

                if consecutive_high_memory >= max_high_memory:
                    logger.critical("Persistent high memory usage, triggering restart...")
                    os._exit(1)  # Force restart through process manager
            else:
                consecutive_high_memory = 0

            logger.info(f"Current memory usage: {memory_usage}MB")
        except Exception as e:
            logger.error(f"Error monitoring memory: {e}")

        time.sleep(300)  # Check every 5 minutes

def keep_alive():
    """Start the keep-alive server and monitoring threads"""
    try:
        server_thread = threading.Thread(target=run)
        ping_thread = threading.Thread(target=ping_server)
        memory_thread = threading.Thread(target=monitor_memory)

        server_thread.daemon = True
        ping_thread.daemon = True
        memory_thread.daemon = True

        server_thread.start()
        ping_thread.start()
        memory_thread.start()

        logger.info("Keep-alive server and monitoring started")
    except Exception as e:
        logger.error(f"Error in keep_alive: {e}")
        raise

def start_keep_alive():
    """Start keep-alive with error handling and retries"""
    max_retries = 5  # Increased from 3 to 5
    retry_count = 0
    retry_delay = 5  # seconds

    while retry_count < max_retries:
        try:
            keep_alive()
            logger.info("Keep-alive server started successfully")
            break
        except Exception as e:
            retry_count += 1
            logger.error(f"Failed to start keep-alive server (attempt {retry_count}): {e}")
            if retry_count < max_retries:
                time.sleep(retry_delay)
            else:
                raise