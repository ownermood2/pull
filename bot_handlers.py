import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio

logger = logging.getLogger(__name__)

class TelegramQuizBot:
    def __init__(self, quiz_manager):
        self.quiz_manager = quiz_manager
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.active_quizzes = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command"""
        chat_id = update.effective_chat.id
        self.quiz_manager.add_active_chat(chat_id)
        logger.info(f"New chat started: {chat_id}")

        welcome_message = """
🎯 Welcome to QuizBot! 

I'll be your quiz master, delivering exciting questions every 20 minutes.
Get ready to test your knowledge and compete with other members!

Commands:
/start - Show this welcome message
/help - Show available commands
/score - Check your score

Let the quiz begin! 🎉
        """
        await update.message.reply_text(welcome_message)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /help command"""
        help_text = """
Available commands:
/start - Start the bot
/help - Show this help message
/score - Check your score
/quiz - Start a quiz manually (admin only)
        """
        await update.message.reply_text(help_text)

    async def send_quiz(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a quiz to a specific chat"""
        logger.info(f"Sending quiz to chat: {chat_id}")
        question = self.quiz_manager.get_random_question()
        if not question:
            logger.warning("No questions available in the database")
            await context.bot.send_message(
                chat_id=chat_id,
                text="No questions available!"
            )
            return

        options = question['options']
        keyboard = [
            [InlineKeyboardButton(opt, callback_data=f"quiz:{i}")]
            for i, opt in enumerate(options)
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🤔 {question['question']}",
            reply_markup=reply_markup
        )
        logger.info(f"Quiz sent successfully to chat {chat_id}")

        self.active_quizzes[message.message_id] = {
            'correct_answer': question['correct_answer'],
            'participants': set()
        }

    async def handle_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle quiz answer callbacks"""
        query = update.callback_query
        user_id = query.from_user.id
        quiz_id = query.message.message_id

        if quiz_id not in self.active_quizzes:
            await query.answer("This quiz has expired!")
            return

        quiz = self.active_quizzes[quiz_id]
        if user_id in quiz['participants']:
            await query.answer("You've already answered!")
            return

        selected_answer = int(query.data.split(':')[1])
        correct = selected_answer == quiz['correct_answer']

        quiz['participants'].add(user_id)

        if correct:
            self.quiz_manager.increment_score(user_id)
            await query.answer("✅ Correct!")
            logger.info(f"User {user_id} answered correctly in chat {query.message.chat_id}")
        else:
            await query.answer("❌ Wrong answer!")
            logger.info(f"User {user_id} answered incorrectly in chat {query.message.chat_id}")

    async def score(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /score command"""
        user_id = update.message.from_user.id
        score = self.quiz_manager.get_score(user_id)
        await update.message.reply_text(f"Your score: {score} points")

async def setup_bot(quiz_manager):
    """Setup and start the Telegram bot"""
    logger.info("Initializing Telegram bot...")
    bot = TelegramQuizBot(quiz_manager)

    # Initialize bot with token
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN not found in environment variables")
        raise ValueError("TELEGRAM_TOKEN environment variable is required")

    application = Application.builder().token(token).build()

    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help))
    application.add_handler(CommandHandler("score", bot.score))
    application.add_handler(CallbackQueryHandler(bot.handle_answer, pattern="^quiz:"))

    # Schedule quiz every 20 minutes
    async def scheduled_quiz(context: ContextTypes.DEFAULT_TYPE):
        logger.info("Starting scheduled quiz distribution")
        active_chats = quiz_manager.get_active_chats()
        logger.info(f"Found {len(active_chats)} active chats")
        for chat_id in active_chats:
            try:
                await bot.send_quiz(chat_id, context)
            except Exception as e:
                logger.error(f"Failed to send quiz to chat {chat_id}: {e}")

    application.job_queue.run_repeating(scheduled_quiz, interval=1200)  # 20 minutes
    logger.info("Quiz scheduler configured")

    # Start the bot
    logger.info("Starting Telegram bot application")
    await application.initialize()
    await application.start()
    await application.run_polling()

    return bot