import os
import logging
import asyncio
import threading
from flask import Flask, render_template, jsonify, request

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default-secret-key")

# Initialize Quiz Manager
try:
    from quiz_manager import QuizManager
    quiz_manager = QuizManager()
    logger.info("Quiz Manager initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Quiz Manager: {e}")
    raise

# Setup Telegram Bot handlers (lazy loading to avoid circular imports)
telegram_bot = None

async def init_bot():
    """Initialize and start the Telegram bot"""
    global telegram_bot
    try:
        from bot_handlers import setup_bot
        telegram_bot = await setup_bot(quiz_manager)
        logger.info("Telegram bot handlers initialized successfully")
        return telegram_bot
    except Exception as e:
        logger.error(f"Failed to initialize Telegram bot: {e}")
        raise

@app.route('/')
def admin_panel():
    return render_template('admin.html')

@app.route('/api/questions', methods=['GET'])
def get_questions():
    return jsonify(quiz_manager.get_all_questions())

@app.route('/api/questions', methods=['POST'])
def add_question():
    data = request.get_json()
    quiz_manager.add_question(
        data['question'],
        data['options'],
        data['correct_answer']
    )
    return jsonify({"status": "success"})

@app.route('/api/questions/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    quiz_manager.delete_question(question_id)
    return jsonify({"status": "success"})

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(init_bot())
        logger.info("Telegram bot started successfully.")
    except Exception as e:
        logger.exception(f"Telegram bot startup failed: {e}")
    finally:
        loop.close()


if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True  # Allow the main thread to exit even if the bot thread is running
    bot_thread.start()
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    except Exception as e:
        logger.exception(f"Application startup failed: {e}")