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
            logger.info("Starting bot initialization...")

            # Build application
            self.application = (
                Application.builder()
                .token(token)
                .build()
            )
            logger.info("Application built successfully")

            # Add handlers
            self.application.add_handler(CommandHandler("start", self.start))
            self.application.add_handler(CommandHandler("help", self.help))
            self.application.add_handler(CommandHandler("score", self.score))
            self.application.add_handler(CallbackQueryHandler(self.handle_answer, pattern="^quiz:"))
            logger.info("Command handlers registered")

            # Schedule quiz every 20 minutes (1200 seconds)
            self.application.job_queue.run_repeating(
                self.scheduled_quiz,
                interval=1200,
                first=10  # Start first quiz after 10 seconds
            )
            logger.info("Quiz scheduler configured successfully")

            # Initialize and start polling
            await self.application.initialize()
            await self.application.start()
            logger.info("Bot started successfully")

            # Start polling in non-blocking mode
            await self.application.updater.start_polling()
            logger.info("Bot polling started")

            return self

        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command"""
        try:
            chat_id = update.effective_chat.id
            logger.info(f"Received /start command in chat {chat_id}")

            self.quiz_manager.add_active_chat(chat_id)

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
            logger.info(f"Sent welcome message to chat {chat_id}")

            # Send first quiz immediately after start
            await self.send_quiz(chat_id, context)

        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await update.message.reply_text("Sorry, there was an error processing your command. Please try again.")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /help command"""
        try:
            help_text = """
Available commands:
/start - Start the bot and enable quizzes
/help - Show this help message
/score - Check your score
            """
            await update.message.reply_text(help_text)
            logger.info(f"Sent help message to chat {update.effective_chat.id}")
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await update.message.reply_text("Sorry, there was an error showing the help message.")

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

    async def scheduled_quiz(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send scheduled quizzes to all active chats"""
        logger.info("Starting scheduled quiz distribution")
        active_chats = self.quiz_manager.get_active_chats()
        logger.info(f"Found {len(active_chats)} active chats")

        for chat_id in active_chats:
            try:
                await self.send_quiz(chat_id, context)
            except Exception as e:
                logger.error(f"Failed to send quiz to chat {chat_id}: {e}")


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