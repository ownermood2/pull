import os
import logging
import traceback
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict, deque
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application,
    CommandHandler,
    PollAnswerHandler,
    ChatMemberHandler,
    ContextTypes,
    CallbackQueryHandler
)
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

class TelegramQuizBot:
    def __init__(self, quiz_manager):
        """Initialize the quiz bot"""
        self.quiz_manager = quiz_manager
        self.application = None
        self.command_cooldowns = defaultdict(lambda: defaultdict(int))
        self.COOLDOWN_PERIOD = 3  # seconds between commands
        self.command_history = defaultdict(lambda: deque(maxlen=10))  # Store last 10 commands per chat
        self.cleanup_interval = 3600  # 1 hour in seconds

    async def check_admin_status(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if bot is admin in the chat"""
        try:
            bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
            return bot_member.status in ['administrator', 'creator']
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return False

    async def send_admin_reminder(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a professional reminder to make bot admin"""
        try:
            # First check if this is a group chat
            chat = await context.bot.get_chat(chat_id)
            if chat.type not in ["group", "supergroup"]:
                return  # Don't send reminder in private chats

            # Then check if bot is already admin
            is_admin = await self.check_admin_status(chat_id, context)
            if is_admin:
                return  # Don't send reminder if bot is already admin

            reminder_message = """🔔 𝗔𝗱𝗺𝗶𝗻 𝗥𝗲𝗾𝘂𝗲𝘀𝘁
════════════════
📌 To enable all quiz features, please:
1. Click Group Settings
2. Select Administrators
3. Add "IIı 𝗤𝘂𝗶𝘇𝗶𝗺𝗽𝗮𝗰𝘁𝗕𝗼𝘁 🇮🇳 ıII" as Admin

🎯 𝗕𝗲𝗻𝗲𝗳𝗶𝘁𝘀
• Automatic Quiz Delivery
• Message Management
• Enhanced Group Analytics
• Leaderboard Updates

✨ Upgrade your quiz experience now!
════════════════"""

            await context.bot.send_message(
                chat_id=chat_id,
                text=reminder_message,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Sent admin reminder to group {chat_id}")

        except Exception as e:
            logger.error(f"Failed to send admin reminder: {e}")

    async def send_quiz(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a quiz to a specific chat using native Telegram quiz format"""
        try:
            # First, try to delete the last quiz if it exists
            try:
                chat_history = self.command_history.get(chat_id, [])
                if chat_history:
                    last_quiz = next((cmd for cmd in reversed(chat_history) if cmd.startswith("/quiz_")), None)
                    if last_quiz:
                        msg_id = int(last_quiz.split("_")[1])
                        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                        logger.info(f"Deleted previous quiz message {msg_id} in chat {chat_id}")
            except Exception as e:
                logger.warning(f"Failed to delete previous quiz: {e}")

            # Get a random question for this specific chat
            question = self.quiz_manager.get_random_question(chat_id)
            if not question:
                await context.bot.send_message(chat_id=chat_id, text="No questions available.")
                logger.warning(f"No questions available for chat {chat_id}")
                return

            # Ensure question text is clean
            question_text = question['question'].strip()
            if question_text.startswith('/addquiz'):
                question_text = question_text[len('/addquiz'):].strip()
                logger.info(f"Cleaned /addquiz prefix from question for chat {chat_id}")

            logger.info(f"Sending quiz to chat {chat_id}. Question: {question_text[:50]}...")

            # Send the poll
            message = await context.bot.send_poll(
                chat_id=chat_id,
                question=question_text,  # Use cleaned question text
                options=question['options'],
                type=Poll.QUIZ,
                correct_option_id=question['correct_answer'],
                is_anonymous=False
            )

            if message and message.poll:
                poll_data = {
                    'chat_id': chat_id,
                    'correct_option_id': question['correct_answer'],
                    'user_answers': {},
                    'poll_id': message.poll.id,
                    'question': question_text,  # Store cleaned question text
                    'timestamp': datetime.now().isoformat()
                }
                # Store using proper poll ID key
                context.bot_data[f"poll_{message.poll.id}"] = poll_data
                logger.info(f"Stored quiz data: poll_id={message.poll.id}, chat_id={chat_id}")
                self.command_history[chat_id].append(f"/quiz_{message.message_id}")

        except Exception as e:
            logger.error(f"Error sending quiz: {str(e)}\n{traceback.format_exc()}")
            await context.bot.send_message(chat_id=chat_id, text="Error sending quiz.")

    async def scheduled_cleanup(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Automatically clean old messages every hour"""
        try:
            active_chats = self.quiz_manager.get_active_chats()
            for chat_id in active_chats:
                try:
                    # Get bot messages older than 2 hours
                    messages_to_delete = []
                    async for message in context.bot.get_chat_history(chat_id, limit=100):
                        if (message.from_user.id == context.bot.id and
                            (datetime.now() - message.date).total_seconds() > 7200):  # 2 hours
                            messages_to_delete.append(message.message_id)

                    # Delete old messages
                    for msg_id in messages_to_delete:
                        try:
                            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                        except Exception:
                            continue

                    logger.info(f"Cleaned {len(messages_to_delete)} old messages from chat {chat_id}")
                except Exception as e:
                    logger.error(f"Error cleaning messages in chat {chat_id}: {e}")

        except Exception as e:
            logger.error(f"Error in scheduled cleanup: {e}")

    async def initialize(self, token: str):
        """Initialize and start the bot"""
        try:
            # Build application
            self.application = (
                Application.builder()
                .token(token)
                .build()
            )

            # Add handlers for all commands
            self.application.add_handler(CommandHandler("start", self.start))
            self.application.add_handler(CommandHandler("help", self.help))
            self.application.add_handler(CommandHandler("quiz", self.quiz_command))
            self.application.add_handler(CommandHandler("category", self.category))
            self.application.add_handler(CommandHandler("mystats", self.mystats))
            self.application.add_handler(CommandHandler("groupstats", self.groupstats))
            self.application.add_handler(CommandHandler("leaderboard", self.leaderboard))

            # Developer commands
            self.application.add_handler(CommandHandler("allreload", self.allreload))
            self.application.add_handler(CommandHandler("addquiz", self.addquiz))
            self.application.add_handler(CommandHandler("globalstats", self.globalstats))
            self.application.add_handler(CommandHandler("editquiz", self.editquiz))
            self.application.add_handler(CommandHandler("delquiz", self.delquiz))
            self.application.add_handler(CommandHandler("delquiz_confirm", self.delquiz_confirm))
            self.application.add_handler(CommandHandler("broadcast", self.broadcast))
            self.application.add_handler(CommandHandler("totalquiz", self.totalquiz))
            self.application.add_handler(CommandHandler("clear_quizzes", self.clear_quizzes))

            # Handle answers and chat member updates
            self.application.add_handler(PollAnswerHandler(self.handle_answer))
            self.application.add_handler(ChatMemberHandler(self.track_chats, ChatMemberHandler.MY_CHAT_MEMBER))

            # Add callback query handler for clear_quizzes confirmation
            self.application.add_handler(CallbackQueryHandler(
                self.handle_clear_quizzes_callback,
                pattern="^clear_quizzes_confirm_(yes|no)$"
            ))

            # Schedule automated quiz job
            self.application.job_queue.run_repeating(
                self.send_automated_quiz,
                interval=1200,  # 20 minutes in seconds
                first=10  # Start first quiz after 10 seconds
            )

            # Schedule cleanup jobs
            self.application.job_queue.run_repeating(
                self.scheduled_cleanup,
                interval=3600,  # Every hour
                first=300
            )
            self.application.job_queue.run_repeating(
                self.cleanup_old_polls,
                interval=3600, #Every Hour
                first=300
            )
            # Add question history cleanup job
            self.application.job_queue.run_repeating(
                lambda context: self.quiz_manager.cleanup_old_questions(),
                interval=3600,  # Every hour
                first=600
            )

            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()

            return self

        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise

    async def track_chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Track when bot is added to or removed from chats"""
        result = self.extract_status_change(update.my_chat_member)

        if result is None:
            return

        was_member, is_member = result

        # Handle chat type
        chat = update.effective_chat
        if chat.type in ["group", "supergroup"]:
            if not was_member and is_member:
                # Bot was added to a group
                self.quiz_manager.add_active_chat(chat.id)
                await self.send_welcome_message(chat.id, context)
                logger.info(f"Bot added to group {chat.title} ({chat.id})")
            elif was_member and not is_member:
                # Bot was removed from a group
                self.quiz_manager.remove_active_chat(chat.id)
                logger.info(f"Bot removed from group {chat.title} ({chat.id})")

    async def send_welcome_message(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send welcome message when bot joins a group"""
        keyboard = [
            [InlineKeyboardButton(
                "🔥 Add to Group/Channel 🔥",
                url=f"https://t.me/{context.bot.username}?startgroup=true"
            )]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        welcome_message = """🎯 Welcome to IIı 𝗤𝘂𝗶𝘇𝗶𝗺𝗽𝗮𝗰𝘁𝗕𝗼𝘁 🇮🇳 ıII 🎉

🚀 𝗪𝗵𝘆 𝗤𝘂𝗶𝘇𝗠𝗮𝘀𝘁𝗲𝗿𝗥𝗼𝗯𝗼𝘁?
➜ Auto Quizzes – Fresh quiz every 20 mins!
➜ Leaderboard – Track scores & compete!
➜ Categories – GK, CA, History & more! /category
➜ Instant Results – Answers in real-time!

📝 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦
/start – Begin your journey
/help – View commands
/category – View topics

🔥 Add me to your groups for quiz fun!"""

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )

            # If it's a group, check admin status and handle accordingly
            chat = await context.bot.get_chat(chat_id)
            if chat.type in ["group", "supergroup"]:
                is_admin = await self.check_admin_status(chat_id, context)
                if is_admin:
                    await self.send_quiz(chat_id, context)
                else:
                    await self.send_admin_reminder(chat_id, context)

            logger.info(f"Sent welcome message to chat {chat_id}")
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")

    async def handle_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle quiz answers"""
        try:
            answer = update.poll_answer
            if not answer or not answer.poll_id or not answer.user:
                logger.warning("Received invalid poll answer")
                return

            logger.info(f"Received answer from user {answer.user.id} for poll {answer.poll_id}")

            # Get quiz data from context using proper key
            poll_data = context.bot_data.get(f"poll_{answer.poll_id}")
            if not poll_data:
                logger.warning(f"No poll data found for poll_id {answer.poll_id}")
                return

            # Check if this is a correct answer
            is_correct = poll_data['correct_option_id'] in answer.option_ids
            chat_id = poll_data['chat_id']

            # Record the answer in poll_data
            poll_data['user_answers'][answer.user.id] = {
                'option_ids': answer.option_ids,
                'is_correct': is_correct,
                'timestamp': datetime.now().isoformat()
            }

            # Record both global and group-specific score
            if is_correct:
                self.quiz_manager.increment_score(answer.user.id)
                logger.info(f"Recorded correct answer for user {answer.user.id}")

            # Record group attempt
            self.quiz_manager.record_group_attempt(
                user_id=answer.user.id,
                chat_id=chat_id,
                is_correct=is_correct
            )
            logger.info(f"Recorded group attempt for user {answer.user.id} in chat {chat_id} (correct: {is_correct})")

        except Exception as e:
            logger.error(f"Error handling answer: {str(e)}\n{traceback.format_exc()}")

    async def quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /quiz command"""
        try:
            if not await self.check_cooldown(update.effective_user.id, "quiz"):
                await update.message.reply_text("Please wait a few seconds before requesting another quiz.")
                return

            await self.send_quiz(update.effective_chat.id, context)
        except Exception as e:
            logger.error(f"Error in quiz command: {e}")
            await update.message.reply_text("Error starting quiz.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command"""
        try:
            chat_id = update.effective_chat.id
            chat_type = update.effective_chat.type
            self.quiz_manager.add_active_chat(chat_id)

            keyboard = [
                [InlineKeyboardButton(
                    "🔥 Add to Group/Channel 🔥",
                    url=f"https://t.me/{context.bot.username}?startgroup=true"
                )]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            welcome_message = """🎯 Welcome to IIı 𝗤𝘂𝗶𝘇𝗶𝗺𝗽𝗮𝗰𝘁𝗕𝗼𝘁 🇮🇳 ıII 🎉

🚀 𝗪𝗵𝘆 𝗤𝘂𝗶𝘇𝗠𝗮𝘀𝘁𝗲𝗿𝗥𝗼𝗯𝗼𝘁?
➜ Auto Quizzes – Fresh quiz every 20 mins!
➜ Leaderboard – Track scores & compete!
➜ Categories – GK, CA, History & more! /category
➜ Instant Results – Answers in real-time!

📝 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦
/start – Begin your journey
/help – View commands
/category – View topics

🔥 Add me to your groups for quiz fun!"""

            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )

            # If it's a group, check admin status and handle accordingly
            if chat_type in ["group", "supergroup"]:
                is_admin = await self.check_admin_status(chat_id, context)
                if is_admin:
                    await self.send_quiz(chat_id, context)
                else:
                    await self.send_admin_reminder(chat_id, context)
            elif chat_type == "private":
                # In private chat, just send a demo quiz
                await self.send_quiz(chat_id, context)

        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await update.message.reply_text("Error starting the bot. Please try again.")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /help command"""
        try:
            # Check if user is developer
            is_dev = await self.is_developer(update.message.from_user.id)

            help_text = """📝 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦
════════════════
🎯 𝗚𝗘𝗡𝗘𝗥𝗔𝗟 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦
/start – Begin your quiz journey
/help – Available commands
/category – View Topics
/quiz – Try a quiz demo

📊 𝗦𝗧𝗔𝗧𝗦 & 𝗟𝗘𝗔𝗗𝗘𝗥𝗕𝗢𝗔𝗥𝗗
/mystats - Your Performance
/groupstats – Your group performance
/leaderboard – See champions"""

            # Add developer commands only for developers
            if is_dev:
                help_text += """

🔒 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦
/allreload – Full bot restart
/addquiz – Add new questions
/globalstats – Bot stats
/editquiz – Modify quizzes
/broadcast – Send announcements
/delquiz - Delete a quiz
/totalquiz - Show total quizzes
/clear_quizzes - Remove all quizzes"""

            help_text += "\n════════════════"

            # Send help message with better error handling
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=help_text,
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"Help message sent to user {update.effective_user.id}")
            except Exception as e:
                logger.error(f"Failed to send help message with markdown: {e}")
                # Try sending without markdown formatting as fallback
                plain_text = help_text.replace('𝗖', 'C').replace('𝗚', 'G').replace('𝗦', 'S')\
                    .replace('𝗟', 'L').replace('𝗗', 'D').replace('𝗠', 'M').replace('𝗘', 'E')\
                    .replace('═', '=').replace('•', '*')
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=plain_text,
                    parse_mode=None
                )

        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await update.message.reply_text("Error showing help. Please try again later.")

    async def category(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /category command"""
        try:
            category_text = """📚 𝗩𝗜𝗘𝗪 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗜𝗘𝗦  
══════════════════  
📑 𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘 𝗤𝗨𝗜𝗭 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗜𝗘𝗦  
• General Knowledge 🌍
• Current Affairs 📰
• Static GK 📚
• Science & Technology 🔬
• History 📜
• Geography 🗺
• Economics 💰
• Political Science 🏛
• Constitution 📖
• Constitution & Law ⚖
• Arts & Literature 🎭
• Sports & Games 🎮  

🎯 Stay tuned! More quizzes coming soon!  
🛠 Need help? Use /help for more commands!"""

            await update.message.reply_text(category_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error showing categories: {e}")
            await update.message.reply_text("Error showing categories.")



    async def mystats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show detailed personal statistics"""
        try:
            user = update.effective_user
            if not user:
                logger.error("No user found in update")
                await update.message.reply_text("Error: Could not identify user.")
                return

            logger.info(f"Processing /mystats command for user {user.id} ({user.first_name})")

            # Get detailed user stats
            stats = self.quiz_manager.get_user_stats(user.id)
            if not stats:
                await update.message.reply_text("No quiz history found. Start taking quizzes to see your stats! 🎯")
                return

            # Calculate streaks and achievements
            current_streak = stats.get('current_streak', 0)
            best_streak = stats.get('best_streak', 0)
            achievements = []
            if stats['correct_answers'] >= 100:
                achievements.append("🏆 Quiz Master")
            if current_streak >= 7:
                achievements.append("🔥 Week Warrior")
            if stats['success_rate'] >= 80:
                achievements.append("⭐ Accuracy Expert")

            stats_message = f"""📊 𝗤𝘂𝗶𝘇 𝗠𝗮𝘀𝘁𝗲𝗿 𝗣𝗲𝗿𝘀𝗼𝗻𝗮𝗹 𝗦𝘁𝗮𝘁𝘀
════════════════
👤 {user.first_name}

🎯 𝗣𝗲𝗿𝗳𝗼𝗿𝗺𝗮𝗻𝗰𝗲
• Total Quizzes: {stats['total_quizzes']}
• Correct Answers: {stats['correct_answers']}
• Success Rate: {stats['success_rate']}%
• Current Score: {stats['current_score']}

🔥 𝗦𝘁𝗿𝗲𝗮𝗸𝘀
• Current Streak: {current_streak} days
• Best Streak: {best_streak} days

📈 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆
• Today: {stats['today_quizzes']} quizzes
• This Week: {stats['week_quizzes']} quizzes
• This Month: {stats['month_quizzes']} quizzes

🏆 𝗔𝗰𝗵𝗶𝗲𝘃𝗲𝗺𝗲𝗻𝘁𝘀
{chr(10).join(achievements) if achievements else "Keep playing to earn achievements!"}
════════════════"""

            try:
                await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)
                logger.info(f"Personal stats shown to user {user.id}")
            except Exception as e:
                logger.error(f"Failed to send stats with markdown: {e}")
                # Fallback to plain text if markdown fails
                plain_text = stats_message.replace('𝗤', 'Q').replace('𝗠', 'M').replace('𝗣', 'P')\
                    .replace('𝗦', 'S').replace('𝗔', 'A').replace('═', '=').replace('•', '*')
                await update.message.reply_text(plain_text)

        except Exception as e:
            logger.error(f"Error in mystats: {str(e)}\n{traceback.format_exc()}")
            await update.message.reply_text("❌ Error retrieving your stats. Please try again.")

    async def groupstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show comprehensive group performance statistics"""
        try:
            chat = update.effective_chat
            if not chat.type.endswith('group'):
                await update.message.reply_text("This command only works in groups! 👥")
                return

            stats = self.quiz_manager.get_group_leaderboard(chat.id)
            if not stats['leaderboard']:
                await update.message.reply_text("No quiz participants in this group yet! Start taking quizzes to appear here! 🎯")
                return

            # Build comprehensive stats message
            stats_message = f"""📊 𝗚𝗿𝗼𝘂𝗽 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀 - {chat.title}
════════════════

📈 𝗚𝗿𝗼𝘂𝗽 𝗣𝗲𝗿𝗳𝗼𝗿𝗺𝗮𝗻𝗰𝗲
• Total Quizzes: {stats['total_quizzes']}
• Correct Answers: {stats['total_correct']}
• Group Accuracy: {stats['group_accuracy']}%
• Active Streak: {stats.get('group_streak', 0)} days

👥 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆 𝗧𝗿𝗮𝗰𝗸𝗶𝗻𝗚
• Active Today: {stats['active_users']['today']} users
• Active This Week: {stats['active_users']['week']} users
• Active This Month: {stats['active_users']['month']} users
• Total Participants: {stats['active_users']['total']} users

🏆 𝗧𝗼𝗽 𝗣𝗲𝗿𝗳𝗼𝗿𝗺𝗲𝗿𝘀"""

            # Add top performers with detailed stats
            for rank, entry in enumerate(stats['leaderboard'][:5], 1):
                try:
                    user = await context.bot.get_chat(entry['user_id'])
                    username = user.first_name or user.username or "Anonymous"
                    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
                    stats_message += f"""

{medals[rank-1]} {username}
   ✅ Total: {entry['total_attempts']} quizzes
   🎯 Correct: {entry['correct_answers']}
   📊 Accuracy: {entry['accuracy']}%
   🔥 Streak: {entry.get('current_streak', 0)}
   ⚡ Last Active: {entry['last_active']}"""
                except Exception as e:
                    logger.error(f"Error getting user info for ID {entry['user_id']}: {e}")
                    continue

            stats_message += "\n\n📱 Real-time stats | Auto-updates every 20 min"
            stats_message += "\n════════════════"

            try:
                await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)
                logger.info(f"Group stats shown in chat {chat.id}")
            except Exception as e:
                logger.error(f"Failed to send stats with markdown: {e}")
                # Fallback to plain text if markdown fails
                plain_text = stats_message.replace('𝗚', 'G').replace('𝗦', 'S').replace('𝗣', 'P')\
                    .replace('𝗔', 'A').replace('𝗧', 'T').replace('═', '=').replace('•', '*')
                await update.message.reply_text(plain_text)

        except Exception as e:
            logger.error(f"Error in groupstats: {e}\n{traceback.format_exc()}")
            await update.message.reply_text("❌ Error retrieving group stats. Please try again.")

    async def globalstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show comprehensive bot statistics - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Get basic stats with error handling
            try:
                active_chats = self.quiz_manager.get_active_chats()
                total_users = len(self.quiz_manager.stats)
                total_groups = len(active_chats)
            except Exception as e:
                logger.error(f"Error getting basic stats: {e}")
                raise

            # Calculate time-based metrics
            try:
                current_date = datetime.now().strftime('%Y-%m-%d')
                today_active_users = sum(
                    1 for stats in self.quiz_manager.stats.values()
                    if stats.get('last_activity_date') == current_date
                )

                week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
                week_active_users = sum(
                    1 for stats in self.quiz_manager.stats.values()
                    if stats.get('last_activity_date', '1970-01-01') >= week_start
                )
            except Exception as e:
                logger.error(f"Error calculating time-based metrics: {e}")
                raise

            # Calculate quiz statistics
            try:
                today_quizzes = sum(
                    stats['daily_activity'].get(current_date, {}).get('attempts', 0)
                    for stats in self.quiz_manager.stats.values()
                )

                week_quizzes = sum(
                    sum(
                        day_stats.get('attempts', 0)
                        for date, day_stats in stats['daily_activity'].items()
                        if date >= week_start
                    )
                    for stats in self.quiz_manager.stats.values()
                )

                # Calculate success rates
                total_attempts = sum(
                    stats.get('total_quizzes', 0)
                    for stats in self.quiz_manager.stats.values()
                )
                correct_answers = sum(
                    stats.get('correct_answers', 0)
                    for stats in self.quiz_manager.stats.values()
                )
                success_rate = (
                    round((correct_answers / total_attempts) * 100, 2)
                    if total_attempts > 0 else 0
                )
            except Exception as e:
                logger.error(f"Error calculating quiz statistics: {e}")
                raise

            stats_message = f"""📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀
════════════════
👥 𝗨𝘀𝗲𝗿𝘀 & 𝗚𝗿𝗼𝘂𝗽𝘀
• Total Users: {total_users}
• Total Groups: {total_groups}
• Active Today: {today_active_users}
• Active This Week: {week_active_users}

📈 𝗤𝘂𝗶𝘇 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆
• Today's Quizzes: {today_quizzes}
• This Week: {week_quizzes}
• Total Attempts: {total_attempts}
• Correct Answers: {correct_answers}
• Success Rate: {success_rate}%

⚡ 𝗥𝗲𝗮𝗹-𝘁𝗶𝗺𝗲 𝗠𝗲𝘁𝗿𝗶𝗰𝘀
• Active Groups Now: {len([c for c in active_chats if self.quiz_manager.get_group_last_activity(c) == current_date])}
• Total Questions: {len(self.quiz_manager.questions)}
════════════════"""

            try:
                await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)
                logger.info(f"Global stats shown to developer {update.effective_user.id}")
            except Exception as e:
                logger.error(f"Failed to send stats with markdown: {e}")
                # Fallback to plain text if markdown fails
                plain_text = stats_message.replace('𝗕', 'B').replace('𝗨', 'U').replace('𝗚', 'G')\
                    .replace('𝗤', 'Q').replace('𝗔', 'A').replace('𝗥', 'R').replace('𝗠', 'M')\
                    .replace('═', '=').replace('•', '*')
                await update.message.reply_text(plain_text)

        except Exception as e:
            logger.error(f"Error in globalstats: {e}\n{traceback.format_exc()}")
            await update.message.reply_text("❌ Error retrieving global statistics. Please try again.")

    async def leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show global leaderboard"""
        try:
            leaderboard = self.quiz_manager.get_leaderboard()

            if not leaderboard:
                await update.message.reply_text("No quiz participants yet! Be the first one to start! 🎯", parse_mode=ParseMode.MARKDOWN)
                return

            # Header
            leaderboard_text = """🏆 𝗚𝗹𝗼𝗯𝗮𝗹 𝗟𝗲𝗮𝗱𝗲𝗿𝗯𝗼𝗮𝗿𝗱
════════════════"""

            # Get user info for each leaderboard entry
            for rank, entry in enumerate(leaderboard[:10], 1):
                try:
                    # Get userinfo from Telegram
                    user = await context.bot.get_chat(entry['user_id'])
                    username = user.first_name or user.username or "Anonymous"

                    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
                    leaderboard_text += f"""

{medals[rank-1]} {username}
   ✅ Total: {entry['total_attempts']}
   🎯 Correct: {entry['correct_answers']}
   ❌ Wrong: {entry['wrong_answers']}
   📊 Accuracy: {entry['accuracy']}%"""
                except Exception as e:
                    logger.error(f"Error getting user info for ID {entry['user_id']}: {e}")
                    continue

            leaderboard_text += "\n\n📱 Real-time rankings | Auto-updates every quiz"
            leaderboard_text += "\n════════════════"

            try:
                await update.message.reply_text(leaderboard_text, parse_mode=ParseMode.MARKDOWN)
                logger.info(f"Leaderboard shown for user {update.effective_user.id}")
            except Exception as e:
                logger.error(f"Failed to send leaderboard with markdown: {e}")
                # Fallback to plain text if markdown fails
                plain_text = leaderboard_text.replace('𝗚', 'G').replace('𝗟', 'L').replace('═', '=')
                await update.message.reply_text(plain_text)

        except Exception as e:
            logger.error(f"Error showing leaderboard: {e}\n{traceback.format_exc()}")
            await update.message.reply_text("❌ Error retrieving leaderboard. Please try again.")

    async def allreload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Full bot restart - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Send initial message
            status_message = await update.message.reply_text("🔄 Initiating full bot reload...")

            try:
                # Save current state
                await status_message.edit_text("📊 Saving current state...")
                active_chats = self.quiz_manager.get_active_chats()
                user_stats = self.quiz_manager.stats.copy()

                # Reload questions and data
                await status_message.edit_text("📝 Reloading quiz database...")
                self.quiz_manager.reload_data()  # This method should exist in QuizManager
                logger.info("Questions and data reloaded successfully")

                # Restore active chats
                await status_message.edit_text("👥 Restoring active chats...")
                for chat_id in active_chats:
                    self.quiz_manager.add_active_chat(chat_id)
                logger.info(f"Restored {len(active_chats)} active chats")

                # Restore user stats
                await status_message.edit_text("👤 Restoring user statistics...")
                self.quiz_manager.stats.update(user_stats)
                logger.info(f"Restored stats for {len(user_stats)} users")

                # Clear any cached data
                if hasattr(self.quiz_manager, '_cached_leaderboard'):
                    self.quiz_manager._cached_leaderboard = None
                if hasattr(self.quiz_manager, '_leaderboard_cache_time'):
                    self.quiz_manager._leaderboard_cache_time = None

                # Verify data integrity
                total_users = len(self.quiz_manager.stats)
                total_groups = len(self.quiz_manager.get_active_chats())
                total_questions = len(self.quiz_manager.questions)

                success_message = f"""✅ Bot Successfully Reloaded!

📊 𝗦𝘁𝗮𝘁𝘂𝘀 𝗥𝗲𝗽𝗼𝗿𝘁
• Active Users: {total_users}
• Active Groups: {total_groups}
• Total Questions: {total_questions}

⚡ All systems operational!"""

                await status_message.edit_text(success_message, parse_mode=ParseMode.MARKDOWN)
                logger.info("Full bot reload completed successfully")

            except Exception as e:
                error_message = f"❌ Error during reload: {str(e)}"
                await status_message.edit_text(error_message)
                logger.error(f"Reload failed: {e}\n{traceback.format_exc()}")
                raise

        except Exception as e:
            logger.error(f"Error in allreload: {e}\n{traceback.format_exc()}")
            await update.message.reply_text("❌ Critical error during reload.")
            raise

    async def addquiz(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Add new quiz(zes) - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Extract message content
            content = update.message.text.split(" ", 1)
            if len(content) < 2:
                await update.message.reply_text(
                    "❌ Please provide questions in the correct format.\n\n"
                    "For single question:\n"
                    "/addquiz question | option1 | option2 | option3 | option4 | correct_number\n\n"
                    "For multiple questions (using the | format):\n"
                    "/addquiz question1 | option1 | option2 | option3 | option4 | correct_number\n"
                    "/addquiz question2 | option1 | option2 | option3 | option4 | correct_number\n\n"
                    "Add more Quiz /addquiz !"
                )
                return

            questions_data = []
            message_text = content[1].strip()

            # Split by newlines to handle multiple questions
            lines = message_text.split('\n')
            for line in lines:
                line = line.strip()
                if not line or not '|' in line:
                    continue

                parts = line.split("|")
                if len(parts) != 6:
                    continue

                try:
                    correct_answer = int(parts[5].strip()) - 1
                    if not (0 <= correct_answer < 4):
                        continue

                    questions_data.append({
                        'question': parts[0].strip(),
                        'options': [p.strip() for p in parts[1:5]],
                        'correct_answer': correct_answer
                    })
                except (ValueError, IndexError):
                    continue

            if not questions_data:
                await update.message.reply_text(
                    "❌ Please provide questions in the correct format.\n\n"
                    "For single question:\n"
                    "/addquiz question | option1 | option2 | option3 | option4 | correct_number\n\n"
                    "For multiple questions (using the | format):\n"
                    "/addquiz question1 | option1 | option2 | option3 | option4 | correct_number\n"
                    "/addquiz question2 | option1 | option2 | option3 | option4 | correct_number\n\n"
                    "Add more Quiz /addquiz !"
                )
                return

            # Add questions and get stats
            stats = self.quiz_manager.add_questions(questions_data)
            total_questions = len(self.quiz_manager.get_all_questions())

            # Format response message
            response = f"""📝 𝗤𝘂𝗶𝘇 𝗔𝗱𝗱𝗶𝘁𝗶𝗼𝗻 𝗥𝗲𝗽𝗼𝗿𝘁
════════════════
✅ Successfully added: {stats['added']} questions

👉 𝗧𝗼𝘁𝗮𝗹 𝗤𝘂𝗶𝘇: {total_questions}

❌ 𝗥𝗲𝗷𝗲𝗰𝘁𝗲𝗱:
• Duplicates: {stats['rejected']['duplicates']}
• Invalid Format: {stats['rejected']['invalid_format']}
• Invalid Options: {stats['rejected']['invalid_options']}
════════════════"""

            await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error(f"Error in addquiz: {e}")
            await update.message.reply_text("❌ Error adding quiz.")

    async def globalstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show comprehensive bot statistics - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Get basic stats with error handling
            try:
                active_chats = self.quiz_manager.get_active_chats()
                total_users = len(self.quiz_manager.stats)
                total_groups = len(active_chats)
            except Exception as e:
                logger.error(f"Error getting basic stats: {e}")
                raise

            # Calculate time-based metrics
            try:
                current_date = datetime.now().strftime('%Y-%m-%d')
                today_active_users = sum(
                    1 for stats in self.quiz_manager.stats.values()
                    if stats.get('last_activity_date') == current_date
                )

                week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
                week_active_users = sum(
                    1 for stats in self.quiz_manager.stats.values()
                    if stats.get('last_activity_date', '1970-01-01') >= week_start
                )
            except Exception as e:
                logger.error(f"Error calculating time-based metrics: {e}")
                raise

            # Calculate quiz statistics
            try:
                today_quizzes = sum(
                    stats['daily_activity'].get(current_date, {}).get('attempts', 0)
                    for stats in self.quiz_manager.stats.values()
                )

                week_quizzes = sum(
                    sum(
                        day_stats.get('attempts', 0)
                        for date, day_stats in stats['daily_activity'].items()
                        if date >= week_start
                    )
                    for stats in self.quiz_manager.stats.values()
                )

                # Calculate success rates
                total_attempts = sum(
                    stats.get('total_quizzes', 0)
                    for stats in self.quiz_manager.stats.values()
                )
                correct_answers = sum(
                    stats.get('correct_answers', 0)
                    for stats in self.quiz_manager.stats.values()
                )
                success_rate = (
                    round((correct_answers / total_attempts) * 100, 2)
                    if total_attempts > 0 else 0
                )
            except Exception as e:
                logger.error(f"Error calculating quiz statistics: {e}")
                raise

            stats_message = f"""📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀
════════════════
👥 𝗨𝘀𝗲𝗿𝘀 & 𝗚𝗿𝗼𝘂𝗽𝘀
• Total Users: {total_users}
• Total Groups: {total_groups}
• Active Today: {today_active_users}
• Active This Week: {week_active_users}

📈 𝗤𝘂𝗶𝘇 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆
• Today's Quizzes: {today_quizzes}
• This Week: {week_quizzes}
• Total Attempts: {total_attempts}
• Correct Answers: {correct_answers}
• Success Rate: {success_rate}%

⚡ 𝗥𝗲𝗮𝗹-𝘁𝗶𝗺𝗲 𝗠𝗲𝘁𝗿𝗶𝗰𝘀
• Active Groups Now: {len([c for c in active_chats if self.quiz_manager.get_group_last_activity(c) == current_date])}
• Total Questions: {len(self.quiz_manager.questions)}
════════════════"""

            try:
                await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)
                logger.info(f"Global stats shown to developer {update.effective_user.id}")
            except Exception as e:
                logger.error(f"Failed to send stats with markdown: {e}")
                # Fallback to plain text if markdown fails
                plain_text = stats_message.replace('𝗕', 'B').replace('𝗨', 'U').replace('𝗚', 'G')\
                    .replace('𝗤', 'Q').replace('𝗔', 'A').replace('𝗥', 'R').replace('𝗠', 'M')\
                    .replace('═', '=').replace('•', '*')
                await update.message.reply_text(plain_text)

        except Exception as e:
            logger.error(f"Error in globalstats: {e}\n{traceback.format_exc()}")
            await update.message.reply_text("❌ Error retrieving global statistics. Please try again.")

    async def editquiz(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show and edit quiz questions - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            logger.info(f"Processing /editquiz command from user {update.message.from_user.id}")

            # Get all questions for validation
            questions = self.quiz_manager.get_all_questions()
            if not questions:
                await update.message.reply_text(
                    """❌ 𝗡𝗼 𝗤𝘂𝗶𝘇𝘇𝗲𝘀 𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲
════════════════
Add new quizzes using /addquiz command
════════════════""",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Handle reply to quiz case
            if update.message.reply_to_message and update.message.reply_to_message.poll:
                poll_id = update.message.reply_to_message.poll.id
                poll_data = context.bot_data.get(f"poll_{poll_id}")

                if not poll_data:
                    await self._handle_quiz_not_found(update, context)
                    return

                # Find the quiz in questions list
                found_idx = -1
                for idx, q in enumerate(questions):
                    if q['question'] == poll_data['question']:
                        found_idx = idx
                        break

                if found_idx == -1:
                    await self._handle_quiz_not_found(update, context)
                    return

                # Show the quiz details
                quiz = questions[found_idx]
                quiz_text = f"""📝 𝗤𝘂𝗶𝘇 𝗗𝗲𝘁𝗮𝗶𝗹𝘀 (#{found_idx + 1})
════════════════

❓ Question: {quiz['question']}
📍 Options:"""
                for i, opt in enumerate(quiz['options'], 1):
                    marker = "✅" if i-1 == quiz['correct_answer'] else "⭕"
                    quiz_text += f"\n{marker} {i}. {opt}"

                quiz_text += """
════════════════

To edit this quiz:
/editquiz {quiz_number}
To delete this quiz:
/delquiz {quiz_number}"""

                await update.message.reply_text(
                    quiz_text,
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Handle direct command case
            # Parse arguments for pagination
            args = context.args
            page = 1
            per_page = 5

            if args and args[0].isdigit():
                page = max(1, int(args[0]))

            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            total_pages = (len(questions) + per_page - 1) // per_page

            # Adjust page if out of bounds
            if page > total_pages:
                page = total_pages
                start_idx = (page - 1) * per_page
                end_idx = start_idx + per_page

            # Format questions for display
            questions_text = f"""📝 𝗤𝘂𝗶𝘇 𝗘𝗱𝗶𝘁𝗼𝗿 (Page {page}/{total_pages})
════════════════

📌 𝗖𝗼𝗺𝗺𝗮𝗻𝗱𝘀:
• View quizzes: /editquiz [page_number]
• Delete quiz: /delquiz [quiz_number]
• Add new quiz: /addquiz

📊 𝗦𝘁𝗮𝘁𝘀:
• Total Quizzes: {len(questions)}
• Showing: #{start_idx + 1} to #{min(end_idx, len(questions))}

🎯 𝗤𝘂𝗶𝘇 𝗟𝗶𝘀𝘁:"""
            for i, q in enumerate(questions[start_idx:end_idx], start=start_idx + 1):
                questions_text += f"""

📌 𝗤𝘂𝗶𝘇 #{i}
❓ Question: {q['question']}
📍 Options:"""
                for j, opt in enumerate(q['options'], 1):
                    marker = "✅" if j-1 == q['correct_answer'] else "⭕"
                    questions_text += f"\n{marker} {j}. {opt}"
                questions_text += "\n════════════════"

            # Add navigation help
            if total_pages > 1:
                questions_text += f"""

📖 𝗡𝗮𝘃𝗶𝗴𝗮𝘁𝗶𝗼𝗻:"""
                if page > 1:
                    questions_text += f"\n⬅️ Previous: /editquiz {page-1}"
                if page < total_pages:
                    questions_text += f"\n➡️ Next: /editquiz {page+1}"

            # Send the formatted message
            await update.message.reply_text(
                questions_text,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Sent quiz list page {page}/{total_pages} to user {update.message.from_user.id}")

        except Exception as e:
            error_msg = f"Error in editquiz command: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            await update.message.reply_text(
                """❌ 𝗘𝗿𝗿𝗼𝗿
════════════════
Failed to display quizzes.
Please try again later.
════════════════""",
                parse_mode=ParseMode.MARKDOWN
            )

    async def _handle_dev_command_unauthorized(self, update: Update) -> None:
        """Handle unauthorized access to developer commands"""
        await update.message.reply_text(
            "⚠️ This command is only available to bot developers.",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.warning(f"Unauthorized access attempt to dev command by user {update.message.from_user.id}")

    async def is_developer(self, user_id: int) -> bool:
        """Check if user is a developer"""
        # Add developer user IDs here
        DEVELOPER_IDS = [7653153066]  # Example developer ID
        return user_id in DEVELOPER_IDS

    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send announcements - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Get message to broadcast
            try:
                message = update.message.text.split(" ", 1)[1]
            except IndexError:
                await update.message.reply_text(
                    "❌ Please provide a message to broadcast.\n"
                    "Format: /broadcast Your message here", parse_mode=ParseMode.MARKDOWN
                )
                return

            active_chats = self.quiz_manager.get_active_chats()
            success_count = 0
            fail_count =0
            # Send to all active chats
            for chat_id in active_chats:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"📢 𝗔𝗻𝗻𝗼𝘂𝗻𝗰𝗲𝗺𝗲𝗻𝘁\n════════════════\n\n{message}", parse_mode=ParseMode.MARKDOWN
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send broadcast to {chat_id}: {e}")
                    fail_count += 1

            await update.message.reply_text(
                f"📢 Broadcast Results:\n"
                f"✅ Successfully sent to: {success_count} chats\n"
                f"❌ Failed to send to: {fail_count} chats", parse_mode=ParseMode.MARKDOWN
            )

        except Exception as e:
            logger.error(f"Error in broadcast: {e}")
            await update.message.reply_text("❌ Error sending broadcast.")

    async def check_admin_status(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if bot is admin in the chat"""
        try:
            bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
            return bot_member.status in ['administrator', 'creator']
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return False

    async def send_admin_reminder(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a professional reminder to make bot admin"""
        try:
            # First check if this is a group chat
            chat = await context.bot.get_chat(chat_id)
            if chat.type not in ["group", "supergroup"]:
                return  # Don't send reminder in private chats

            # Then check if bot is already admin
            is_admin = await self.check_admin_status(chat_id, context)
            if is_admin:
                return  # Don't send reminder if bot is already admin

            reminder_message = """🔔 𝗔𝗱𝗺𝗶𝗻 𝗥𝗲𝗾𝘂𝗲𝘀𝘁
════════════════
📌 To enable all quiz features, please:
1. Click Group Settings
2. Select Administrators
3. Add "IIı 𝗤𝘂𝗶𝘇𝗶𝗺𝗽𝗮𝗰𝘁𝗕𝗼𝘁 🇮🇳 ıII" as Admin

🎯 𝗕𝗲𝗻𝗲𝗳𝗶𝘁𝘀
• Automatic Quiz Delivery
• Message Management
• Enhanced Group Analytics
• Leaderboard Updates

✨ Upgrade your quiz experience now!
════════════════"""

            await context.bot.send_message(
                chat_id=chat_id,
                text=reminder_message,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Sent admin reminder to group {chat_id}")

        except Exception as e:
            logger.error(f"Failed to send admin reminder: {e}")

    async def scheduled_quiz(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send scheduled quizzes to all active chats"""
        try:
            active_chats = self.quiz_manager.get_active_chats()
            for chat_id in active_chats:
                try:
                    # Check if bot is admin
                    is_admin = await self.check_admin_status(chat_id, context)

                    if is_admin:
                        # Clean old messages first
                        try:
                            messages_to_delete = []
                            async for message in context.bot.get_chat_history(chat_id, limit=100):
                                if (message.from_user.id == context.bot.id and
                                    (datetime.now() - message.date).total_seconds() > 3600):  # Delete messages older than 1 hour
                                    messages_to_delete.append(message.message_id)

                            for msg_id in messages_to_delete:
                                try:
                                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                                except Exception:
                                    continue
                        except Exception as e:
                            logger.error(f"Error cleaning old messages in chat {chat_id}: {e}")

                        # Send new quiz
                        await self.send_quiz(chat_id, context)
                        logger.info(f"Sent scheduled quiz to chat {chat_id}")
                    else:
                        # Send admin reminder
                        await self.send_admin_reminder(chat_id, context)
                        logger.info(f"Sent admin reminder to chat {chat_id}")

                except Exception as e:
                    logger.error(f"Error handling chat {chat_id}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in scheduled quiz: {e}")

    async def check_cooldown(self, user_id: int, command: str) -> bool:
        """Check if command is on cooldown for user"""
        current_time = datetime.now().timestamp()
        last_used = self.command_cooldowns[user_id][command]
        if current_time - last_used < self.COOLDOWN_PERIOD:
            return False
        self.command_cooldowns[user_id][command] = current_time
        return True

    async def cleanup_old_polls(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Remove old poll data to prevent memory leaks"""
        try:
            current_time = datetime.now()
            keys_to_remove = []

            for key, poll_data in context.bot_data.items():
                if not key.startswith('poll_'):
                    continue

                # Remove polls older than 1 hour
                if 'timestamp' in poll_data:
                    poll_time = datetime.fromisoformat(poll_data['timestamp'])
                    if (current_time - poll_time) > timedelta(hours=1):
                        keys_to_remove.append(key)

            for key in keys_to_remove:
                del context.bot_data[key]

            logger.info(f"Cleaned up {len(keys_to_remove)} old poll entries")

        except Exception as e:
            logger.error(f"Error cleaning up old polls: {e}")

    async def delquiz(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show and delete quiz questions - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Get all questions for validation
            questions = self.quiz_manager.get_all_questions()
            if not questions:
                await update.message.reply_text(
                    """❌ 𝗡𝗼 𝗤𝘂𝗶𝘇𝘇𝗲𝘀 𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲
════════════════
Add new quizzes using /addquiz command
════════════════""",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Handle reply to quiz case
            if update.message.reply_to_message and update.message.reply_to_message.poll:
                poll_id = update.message.reply_to_message.poll.id
                poll_data = context.bot_data.get(f"poll_{poll_id}")

                if not poll_data:
                    await self._handle_quiz_not_found(update, context)
                    return

                # Find the quiz in questions list
                found_idx = -1
                for idx, q in enumerate(questions):
                    if q['question'] == poll_data['question']:
                        found_idx = idx
                        break

                if found_idx == -1:
                    await self._handle_quiz_not_found(update, context)
                    return

                # Show confirmation message
                quiz = questions[found_idx]
                confirm_text = f"""🗑 𝗖𝗼𝗻𝗳𝗶𝗿𝗺 𝗗𝗲𝗹𝗲𝘁𝗶𝗼𝗻
════════════════

📌 𝗤𝘂𝗶𝘇 #{found_idx + 1}
❓ Question: {quiz['question']}

📍 𝗢𝗽𝘁𝗶𝗼𝗻𝘀:"""
                for i, opt in enumerate(quiz['options'], 1):
                    marker = "✅" if i-1 == quiz['correct_answer'] else "⭕"
                    confirm_text += f"\n{marker} {i}. {opt}"

                confirm_text += f"""

⚠️ 𝗧𝗼 𝗰𝗼𝗻𝗳𝗶𝗿𝗺 𝗱𝗲𝗹𝗲𝘁𝗶𝗼𝗻:
/delquiz_confirm {found_idx + 1}

❌ 𝗧𝗼 𝗰𝗮𝗻𝗰𝗲𝗹:
Use any other command or ignore this message
════════════════"""

                await update.message.reply_text(
                    confirm_text,
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Handle direct command case - check if quiz number is provided
            if not context.args:
                await update.message.reply_text(
                    """❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗨𝘀𝗮𝗴𝗲
════════════════
Either:
1. Reply to a quiz message with /delquiz
2. Use: /delquiz [quiz_number]

ℹ️ Use /editquiz to view available quizzes
════════════════""",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            try:
                quiz_num = int(context.args[0])
                if not (1 <= quiz_num <= len(questions)):
                    await update.message.reply_text(
                        f"""❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗤𝘂𝗶𝘇 𝗡𝘂𝗺𝗯𝗲𝗿
════════════════
Please choose a number between 1 and {len(questions)}

ℹ️ Use /editquiz to view available quizzes
════════════════""",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return

                # Show confirmation message
                quiz = questions[quiz_num - 1]
                confirm_text = f"""🗑 𝗖𝗼𝗻𝗳𝗶𝗿𝗺 𝗗𝗲𝗹𝗲𝘁𝗶𝗼𝗻
════════════════

📌 𝗤𝘂𝗶𝘇 #{quiz_num}
❓ Question: {quiz['question']}

📍 𝗢𝗽𝘁𝗶𝗼𝗻𝘀:"""
                for i, opt in enumerate(quiz['options'], 1):
                    marker = "✅" if i-1 == quiz['correct_answer'] else "⭕"
                    confirm_text += f"\n{marker} {i}. {opt}"

                confirm_text += f"""

⚠️ 𝗧𝗼 𝗰𝗼𝗻𝗳𝗶𝗿𝗺 𝗱𝗲𝗹𝗲𝘁𝗶𝗼𝗻:
/delquiz_confirm {quiz_num}

❌ 𝗧𝗼 𝗰𝗮𝗻𝗰𝗲𝗹:
Use any other command or ignore this message
════════════════"""

                await update.message.reply_text(
                    confirm_text,
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"Sent deletion confirmation for quiz #{quiz_num}")

            except ValueError:
                await update.message.reply_text(
                    """❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗜𝗻𝗽𝘂𝘁
════════════════
Please provide a valid number.

📝 Usage:
/delquiz [quiz_number]

ℹ️ Use /editquiz to view available quizzes
════════════════""",
                    parse_mode=ParseMode.MARKDOWN
                )

        except Exception as e:
            error_msg = f"Error in delquiz command: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            await update.message.reply_text(
                """❌ 𝗘𝗿𝗿𝗼𝗿
════════════════
Failed to process delete request.
Please try again later.
════════════════""",
                parse_mode=ParseMode.MARKDOWN
            )

    async def delquiz_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Confirm and execute quiz deletion - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            if not context.args:
                await update.message.reply_text(
                    """❌ 𝗠𝗶𝘀𝘀𝗶𝗻𝗴 𝗤𝘂𝗶𝘇 𝗡𝘂𝗺𝗯𝗲𝗿
════════════════
Please provide the quiz number to confirm deletion.

📝 Usage:
/delquiz_confirm [quiz_number]
════════════════""",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            try:
                quiz_num = int(context.args[0])
                questions = self.quiz_manager.get_all_questions()

                if not (1 <= quiz_num <= len(questions)):
                    await update.message.reply_text(
                        f"""❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗤𝘂𝗶𝘇 𝗡𝘂𝗺𝗯𝗲𝗿
════════════════
Please choose a number between 1 and {len(questions)}

ℹ️ Use /editquiz to view available quizzes
════════════════""",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return

                # Delete the quiz
                self.quiz_manager.delete_question(quiz_num - 1)
                remaining = len(self.quiz_manager.get_all_questions())

                await update.message.reply_text(
                    f"""✅ 𝗤𝘂𝗶𝘇 𝗗𝗲𝗹𝗲𝘁𝗲𝗱
════════════════
Successfully deleted quiz #{quiz_num}

📊 𝗦𝘁𝗮𝘁𝘀:
• Remaining quizzes: {remaining}

ℹ️ Use /editquiz to view remaining quizzes
════════════════""",
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"Successfully deleted quiz #{quiz_num}")

            except ValueError:
                await update.message.reply_text(
                    """❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗜𝗻𝗽𝘂𝘁
════════════════
Please provide a valid number.

📝 Usage:
/delquiz_confirm [quiz_number]
════════════════""",
                    parse_mode=ParseMode.MARKDOWN
                )

        except Exception as e:
            error_msg = f"Error in delquiz_confirm command: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            await update.message.reply_text(
                """❌ 𝗘𝗿𝗿𝗼𝗿
════════════════
Failed to delete quiz.
Please try again later.
════════════════""",
                parse_mode=ParseMode.MARKDOWN
            )

    async def totalquiz(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show total number of quizzes - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            ## Force reload questions
            total_questions = len(self.quiz_manager.get_all_questions())
            logger.info(f"Total questions count: {total_questions}")

            response = f"""📊 𝗤𝘂𝗶𝘇 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀
════════════════
📚 Total Quizzes Available: {total_questions}
════════════════

Use /addquiz to add more quizzes!
Use/help to see all commands."""

            await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
            logger.info(f"Sent quiz count to user {update.message.from_user.id}")

        except Exception as e:
            logger.error(f"Error in totalquiz command: {e}\n{traceback.format_exc()}")
            await update.message.reply_text("❌ Error getting total quiz count.")

    async def send_automated_quiz(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send automated quiz to all active group chats"""
        try:
            active_chats = self.quiz_manager.get_active_chats()
            logger.info(f"Starting automated quiz broadcast to {len(active_chats)} active chats")

            for chat_id in active_chats:
                try:
                    # Check if chat is a group and bot is admin
                    chat = await context.bot.get_chat(chat_id)
                    if chat.type not in ["group", "supergroup"]:
                        logger.info(f"Skipping non-group chat {chat_id}")
                        continue

                    is_admin = await self.check_admin_status(chat_id, context)
                    if not is_admin:
                        logger.warning(f"Bot is not admin in chat {chat_id}, sending reminder")
                        await self.send_admin_reminder(chat_id, context)
                        continue

                    # Send quiz directly without announcement
                    await self.send_quiz(chat_id, context)
                    logger.info(f"Successfully sent automated quiz to chat {chat_id}")

                except Exception as e:
                    logger.error(f"Failed to send automated quiz to chat {chat_id}: {str(e)}\n{traceback.format_exc()}")
                    continue

            logger.info("Completed automated quiz broadcast cycle")

        except Exception as e:
            logger.error(f"Error in automated quiz broadcast: {str(e)}\n{traceback.format_exc()}")

    async def send_quiz(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a quiz to a specific chat using native Telegram quiz format"""
        try:
            # First, try to delete the last quiz if it exists
            try:
                chat_history = self.command_history.get(chat_id, [])
                if chat_history:
                    last_quiz = next((cmd for cmd in reversed(chat_history) if cmd.startswith("/quiz_")), None)
                    if last_quiz:
                        msg_id = int(last_quiz.split("_")[1])
                        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                        logger.info(f"Deleted previous quiz message {msg_id} in chat {chat_id}")
            except Exception as e:
                logger.warning(f"Failed to delete previous quiz: {e}")

            # Get a random question for this specific chat
            question = self.quiz_manager.get_random_question(chat_id)
            if not question:
                await context.bot.send_message(chat_id=chat_id, text="No questions available.")
                logger.warning(f"No questions available for chat {chat_id}")
                return

            # Ensure question text is clean
            question_text = question['question'].strip()
            if question_text.startswith('/addquiz'):
                question_text = question_text[len('/addquiz'):].strip()
                logger.info(f"Cleaned /addquiz prefix from question for chat {chat_id}")

            logger.info(f"Sending quiz to chat {chat_id}. Question: {question_text[:50]}...")

            # Send the poll
            message = await context.bot.send_poll(
                chat_id=chat_id,
                question=question_text,  # Use cleaned question text
                options=question['options'],
                type=Poll.QUIZ,
                correct_option_id=question['correct_answer'],
                is_anonymous=False
            )

            if message and message.poll:
                poll_data = {
                    'chat_id': chat_id,
                    'correct_option_id': question['correct_answer'],
                    'user_answers': {},
                    'poll_id': message.poll.id,
                    'question': question_text,  # Store cleaned question text
                    'timestamp': datetime.now().isoformat()
                }
                # Store using proper poll ID key
                context.bot_data[f"poll_{message.poll.id}"] = poll_data
                logger.info(f"Stored quiz data: poll_id={message.poll.id}, chat_id={chat_id}")
                self.command_history[chat_id].append(f"/quiz_{message.message_id}")

        except Exception as e:
            logger.error(f"Error sending quiz: {str(e)}\n{traceback.format_exc()}")
            await context.bot.send_message(chat_id=chat_id, text="Error sending quiz.")

    async def _handle_quiz_not_found(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle cases where quiz data is not found"""
        await update.message.reply_text(
            """❌ 𝗤𝘂𝗶𝘇 𝗡𝗼𝘁 𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲
════════════════
This quiz message is too old or no longer exists.
Please use /editquiz to view all available quizzes.
════════════════""",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.warning(f"Quiz not found in reply-to message from user {update.message.from_user.id}")

    async def _handle_invalid_quiz_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE, command: str) -> None:
        """Handle invalid quiz reply messages"""
        await update.message.reply_text(
            f"""❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗥𝗲𝗽𝗹𝘆
════════════════
Please reply to a quiz message or use:
/{command} [quiz_number]

ℹ️ Use /editquiz to view all quizzes
════════════════""",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.warning(f"Invalid quiz reply for {command} from user {update.message.from_user.id}")

    async def clear_quizzes(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clear all quizzes from database with confirmation - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Create confirmation keyboard
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes", callback_data="clear_quizzes_confirm_yes"),
                    InlineKeyboardButton("❌ No", callback_data="clear_quizzes_confirm_no")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send confirmation message
            confirmation_message = """⚠️ 𝗖𝗼𝗻𝗳𝗶𝗿𝗺 𝗗𝗲𝗹𝗲𝘁𝗶𝗼𝗻
════════════════
Are you sure you want to delete ALL quizzes?
This action cannot be undone.

• All questions will be removed
• Quiz history will be cleared
• Stats will remain intact

Please confirm your choice:
════════════════"""

            # Store original message ID for cleanup
            sent_message = await update.message.reply_text(
                confirmation_message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )

            # Store message IDs for cleanup
            if 'cleanup_messages' not in context.user_data:
                context.user_data['cleanup_messages'] = []
            context.user_data['cleanup_messages'].extend([update.message.message_id, sent_message.message_id])

        except Exception as e:
            logger.error(f"Error in clear_quizzes: {e}")
            await update.message.reply_text("Error starting quiz deletion process.")

    async def handle_clear_quizzes_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle clear quizzes confirmation callback"""
        try:
            query = update.callback_query
            await query.answer()  # Acknowledge the button click

            if query.data == "clear_quizzes_confirm_yes":
                # Clear all questions
                result = self.quiz_manager.clear_all_questions()

                response = f"""📊 𝗤𝘂𝗶𝘇 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗖𝗹𝗲𝗮𝗿𝗲𝗱
════════════════
• Total Quizzes Removed: {result['initial_count']}
• Database Status: Clean ✨

✅ Ready to add new quizzes!
Use /addquiz to add new questions.
════════════════"""

            else:
                response = """🔄 𝗢𝗽𝗲𝗿𝗮𝘁𝗶𝗼𝗻 𝗖𝗮𝗻𝗰𝗲𝗹𝗹𝗲𝗱
════════════════
Quiz database remains unchanged.
════════════════"""

            # Edit the confirmation message to show theresult

            # Edit the confirmation message to show the result
            await query.edit_message_text(
                text=response,
                parse_mode=ParseMode.MARKDOWN
            )

            # Clean up messages after a delay
            if 'cleanup_messages' in context.user_data:
                await asyncio.sleep(10)  # Wait 10 seconds
                for msg_id in context.user_data['cleanup_messages']:
                    try:
                        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
                    except Exception as e:
                        logger.error(f"Error deleting message {msg_id}: {e}")
                context.user_data['cleanup_messages'] = []

        except Exception as e:
            logger.error(f"Error in clear_quizzes callback: {e}")
            await query.edit_message_text("Error processing quiz deletion.")

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

    def extract_status_change(chat_member_update):
        """Extract whetherbot was added or removed."""
        try:
            if not chat_member_update or not hasattr(chat_member_update, 'difference'):
                return None

            status_change = chat_member_update.difference().get("status")
            if status_change is None:
                return None

            old_status = chat_member_update.old_chat_member.status
            new_status = chat_member_update.new_chat_member.status

            was_member = old_status in ["member", "administrator", "creator"]
            is_member = new_status in ["member", "administrator", "creator"]

            return was_member, is_member
        except Exception as e:
            logger.error(f"Error in extract_status_change: {e}")
            return None

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