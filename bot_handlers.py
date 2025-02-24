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
        self.quiz_manager = quiz_manager
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
/start - Start the bot and enable quizzes in this chat
/help - Show available commands
/score - Check your score

Let the quiz begin! 🎉
        """
        await update.message.reply_text(welcome_message)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /help command"""
        help_text = """
Available commands:
/start - Start the bot and enable quizzes
/help - Show this help message
/score - Check your score
        """
        await update.message.reply_text(help_text)

    async def send_quiz(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a quiz to a specific chat"""
        try:
            logger.info(f"Sending quiz to chat: {chat_id}")
            question = self.quiz_manager.get_random_question()

            if not question:
                logger.warning("No questions available in the database")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="No questions available at the moment!"
                )
                return

            # Create inline keyboard with options
            keyboard = [
                [InlineKeyboardButton(text=opt, callback_data=f"quiz:{i}")]
                for i, opt in enumerate(question['options'])
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

        except Exception as e:
            logger.error(f"Error sending quiz to chat {chat_id}: {e}")
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Sorry, there was an error sending the quiz. Please try again later!"
                )
            except Exception as send_error:
                logger.error(f"Failed to send error message to chat {chat_id}: {send_error}")

    async def handle_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle quiz answer callbacks"""
        query = update.callback_query
        user_id = query.from_user.id
        quiz_id = query.message.message_id

        try:
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

        except Exception as e:
            logger.error(f"Error handling answer from user {user_id}: {e}")
            await query.answer("Sorry, there was an error processing your answer!")

    async def score(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /score command"""
        try:
            user_id = update.message.from_user.id
            score = self.quiz_manager.get_score(user_id)
            await update.message.reply_text(f"Your score: {score} points 🏆")
        except Exception as e:
            logger.error(f"Error getting score for user {update.message.from_user.id}: {e}")
            await update.message.reply_text("Sorry, there was an error getting your score!")

async def setup_bot(quiz_manager):
    """Setup and start the Telegram bot"""
    logger.info("Initializing Telegram bot...")

    # Verify token
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN not found in environment variables")
        raise ValueError("TELEGRAM_TOKEN environment variable is required")

    try:
        # Create bot instance
        bot = TelegramQuizBot(quiz_manager)

        # Initialize application
        application = Application.builder().token(token).build()

        # Add command handlers
        application.add_handler(CommandHandler("start", bot.start))
        application.add_handler(CommandHandler("help", bot.help))
        application.add_handler(CommandHandler("score", bot.score))
        application.add_handler(CallbackQueryHandler(bot.handle_answer, pattern="^quiz:"))

        # Set up quiz scheduler
        async def scheduled_quiz(context: ContextTypes.DEFAULT_TYPE) -> None:
            logger.info("Starting scheduled quiz distribution")
            active_chats = quiz_manager.get_active_chats()
            logger.info(f"Found {len(active_chats)} active chats")

            for chat_id in active_chats:
                try:
                    await bot.send_quiz(chat_id, context)
                except Exception as e:
                    logger.error(f"Failed to send quiz to chat {chat_id}: {e}")

        # Schedule quiz every 20 minutes (1200 seconds)
        application.job_queue.run_repeating(
            scheduled_quiz,
            interval=1200,
            first=10  # Start first quiz after 10 seconds
        )
        logger.info("Quiz scheduler configured successfully")

        # Initialize and start application
        logger.info("Starting Telegram bot application")
        await application.initialize()
        await application.start()
        await application.run_polling(allowed_updates=Update.ALL_TYPES)

        return bot

    except Exception as e:
        logger.error(f"Failed to setup Telegram bot: {e}")
        raise