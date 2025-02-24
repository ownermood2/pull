import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

logger = logging.getLogger(__name__)

class TelegramQuizBot:
    def __init__(self, quiz_manager):
        """Initialize the quiz bot"""
        self.quiz_manager = quiz_manager
        self.active_quizzes = {}
        self.application = None

    async def initialize(self, token: str):
        """Initialize and start the bot"""
        try:
            # Build application
            self.application = (
                Application.builder()
                .token(token)
                .build()
            )

            # Add handlers
            self.application.add_handler(CommandHandler("start", self.start))
            self.application.add_handler(CommandHandler("help", self.help))
            self.application.add_handler(CommandHandler("score", self.score))
            self.application.add_handler(CallbackQueryHandler(self.handle_answer, pattern="^quiz:"))

            # Schedule quiz every 20 minutes (1200 seconds)
            self.application.job_queue.run_repeating(
                self.scheduled_quiz,
                interval=1200,
                first=10
            )

            # Initialize and start polling
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            return self

        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command"""
        try:
            chat_id = update.effective_chat.id
            self.quiz_manager.add_active_chat(chat_id)

            welcome_message = "Quiz Bot activated. Quizzes will be sent every 20 minutes.\nUse /help to see available commands."
            await update.message.reply_text(welcome_message)

            # Send first quiz immediately
            await self.send_quiz(chat_id, context)

        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await update.message.reply_text("Error starting the bot. Please try again.")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /help command"""
        try:
            help_text = "Commands:\n/start - Activate quizzes\n/help - Show commands\n/score - Check your score"
            await update.message.reply_text(help_text)
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await update.message.reply_text("Error showing help. Please try again.")

    async def send_quiz(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a quiz to a specific chat"""
        try:
            question = self.quiz_manager.get_random_question()
            if not question:
                await context.bot.send_message(chat_id=chat_id, text="No questions available.")
                return

            keyboard = [
                [InlineKeyboardButton(text=opt, callback_data=f"quiz:{i}")]
                for i, opt in enumerate(question['options'])
            ]

            message = await context.bot.send_message(
                chat_id=chat_id,
                text=question['question'],
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            self.active_quizzes[message.message_id] = {
                'correct_answer': question['correct_answer'],
                'participants': set()
            }

        except Exception as e:
            logger.error(f"Error sending quiz: {e}")
            await context.bot.send_message(chat_id=chat_id, text="Error sending quiz.")

    async def handle_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle quiz answer callbacks"""
        query = update.callback_query
        try:
            quiz_id = query.message.message_id
            user_id = query.from_user.id

            if quiz_id not in self.active_quizzes:
                await query.answer("Quiz expired")
                return

            quiz = self.active_quizzes[quiz_id]
            if user_id in quiz['participants']:
                await query.answer("Already answered")
                return

            selected_answer = int(query.data.split(':')[1])
            correct = selected_answer == quiz['correct_answer']
            quiz['participants'].add(user_id)

            if correct:
                self.quiz_manager.increment_score(user_id)
                await query.answer("Correct")
            else:
                await query.answer("Wrong")

        except Exception as e:
            logger.error(f"Error handling answer: {e}")
            await query.answer("Error processing answer")

    async def score(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /score command"""
        try:
            user_id = update.message.from_user.id
            score = self.quiz_manager.get_score(user_id)
            await update.message.reply_text(f"Your score: {score}")
        except Exception as e:
            logger.error(f"Error getting score: {e}")
            await update.message.reply_text("Error getting score")

    async def scheduled_quiz(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send scheduled quizzes to all active chats"""
        try:
            active_chats = self.quiz_manager.get_active_chats()
            for chat_id in active_chats:
                await self.send_quiz(chat_id, context)
        except Exception as e:
            logger.error(f"Error in scheduled quiz: {e}")

async def setup_bot(quiz_manager):
    """Setup and start the Telegram bot"""
    logger.info("Setting up Telegram bot...")
    try:
        # Create bot instance
        bot = TelegramQuizBot(quiz_manager)

        # Get bot token
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_TOKEN environment variable is required")

        # Initialize and start the bot
        await bot.initialize(token)
        return bot

    except Exception as e:
        logger.error(f"Failed to setup Telegram bot: {e}")
        raise