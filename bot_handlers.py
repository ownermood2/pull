import os
import logging
from telegram import Update, Poll
from telegram.ext import (
    Application,
    CommandHandler,
    PollAnswerHandler,
    ContextTypes
)

logger = logging.getLogger(__name__)

class TelegramQuizBot:
    def __init__(self, quiz_manager):
        """Initialize the quiz bot"""
        self.quiz_manager = quiz_manager
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
            self.application.add_handler(CommandHandler("category", self.category)) # Added category handler
            self.application.add_handler(PollAnswerHandler(self.handle_answer))

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

            # Get bot info for the profile link
            bot = await context.bot.get_me()
            bot_username = bot.username

            welcome_message = f"""🎯 Welcome to IIı 𝗤𝘂𝗶𝘇𝗶𝗺𝗽𝗮𝗰𝘁_𝗕𝗼𝘁 [{bot_username}](tg://user?id={bot.id}) 🇮🇳 ıII 🎉

🚀 𝗪𝗵𝘆 𝗤𝘂𝗶𝘇𝗠𝗮𝘀𝘁𝗲𝗿𝗥𝗼𝗯𝗼𝘁?
➜ Auto Quizzes – Fresh quiz every 20 mins!
➜ Leaderboard – Track scores & compete!
➜ Categories – GK, CA, History & more! /category
➜ Instant Results – Answers in real-time!

📝 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦
/start – Begin your journey
/help – View commands
/category – View topics

🔥 Add me as an admin & let's make learning fun!"""

            await update.message.reply_text(
                welcome_message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )

            # Send first quiz immediately
            await self.send_quiz(chat_id, context)

        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await update.message.reply_text("Error starting the bot. Please try again.")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /help command"""
        try:
            help_text = "Commands:\n/start - Activate quizzes\n/help - Show commands\n/score - Check your score\n/category - View available categories" #added category command
            await update.message.reply_text(help_text)
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await update.message.reply_text("Error showing help.")

    async def send_quiz(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a quiz to a specific chat using native Telegram quiz format"""
        try:
            question = self.quiz_manager.get_random_question()
            if not question:
                await context.bot.send_message(chat_id=chat_id, text="No questions available.")
                return

            await context.bot.send_poll(
                chat_id=chat_id,
                question=question['question'],
                options=question['options'],
                type=Poll.QUIZ,
                correct_option_id=question['correct_answer'],
                is_anonymous=False
            )

        except Exception as e:
            logger.error(f"Error sending quiz: {e}")
            await context.bot.send_message(chat_id=chat_id, text="Error sending quiz.")

    async def handle_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle quiz answers from Telegram's native quiz"""
        try:
            answer = update.poll_answer
            if answer.user.id and answer.option_ids:
                # For native quizzes, Telegram handles showing correct/wrong answer
                # We just need to update the score if correct
                poll = context.bot_data.get(answer.poll_id)
                if poll and poll.correct_option_id in answer.option_ids:
                    self.quiz_manager.increment_score(answer.user.id)

        except Exception as e:
            logger.error(f"Error handling answer: {e}")

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

    async def category(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /category command"""
        try:
            categories = self.quiz_manager.get_categories() #Assumed method in quiz_manager
            if categories:
                await update.message.reply_text(f"Available Categories:\n{', '.join(categories)}")
            else:
                await update.message.reply_text("No categories available.")
        except Exception as e:
            logger.error(f"Error getting categories: {e}")
            await update.message.reply_text("Error getting categories.")



async def setup_bot(quiz_manager):
    """Setup and start the Telegram bot"""
    logger.info("Setting up Telegram bot...")
    try:
        bot = TelegramQuizBot(quiz_manager)
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_TOKEN environment variable is required")
        await bot.initialize(token)
        return bot
    except Exception as e:
        logger.error(f"Failed to setup Telegram bot: {e}")
        raise