import os
import logging
import threading
import time
import psutil
import requests
from flask import Flask, jsonify
from datetime import datetime

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
    """Health check endpoint"""
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
    keep_alive_app.run(host='0.0.0.0', port=5000)

def ping_server():
    """Ping server every 5 minutes to keep it alive"""
    while True:
        try:
            requests.get(f"https://{os.environ['REPL_SLUG']}.{os.environ['REPL_OWNER']}.repl.co")
            logger.info("Server pinged successfully")
        except Exception as e:
            logger.error(f"Failed to ping server: {e}")
        time.sleep(300)  # Wait 5 minutes

def monitor_memory():
    """Monitor and manage memory usage"""
    while True:
        try:
            process = psutil.Process(os.getpid())
            memory_usage = process.memory_info().rss / 1024 / 1024  # Convert to MB

            if memory_usage > 500:  # If memory usage exceeds 500MB
                logger.warning(f"High memory usage detected: {memory_usage}MB")
                # Trigger garbage collection
                import gc
                gc.collect()

            logger.info(f"Current memory usage: {memory_usage}MB")
        except Exception as e:
            logger.error(f"Error monitoring memory: {e}")
        time.sleep(3600)  # Check every hour

def keep_alive():
    """Start the keep-alive server and monitoring threads"""
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

def start_keep_alive():
    """Start keep-alive with error handling and retries"""
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            keep_alive()
            logger.info("Keep-alive server started successfully")
            break
        except Exception as e:
            retry_count += 1
            logger.error(f"Failed to start keep-alive server (attempt {retry_count}): {e}")
            if retry_count < max_retries:
                time.sleep(5)  # Wait 5 seconds before retrying
            else:
                raise