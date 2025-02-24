import os
import logging
import traceback
from datetime import datetime, timedelta
from collections import defaultdict, deque
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    PollAnswerHandler,
    ChatMemberHandler,
    ContextTypes
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

            question = self.quiz_manager.get_random_question()
            if not question:
                await context.bot.send_message(chat_id=chat_id, text="No questions available.")
                return

            # Send the poll
            message = await context.bot.send_poll(
                chat_id=chat_id,
                question=question['question'],
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
                    'question': question['question'],
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
            self.application.add_handler(CommandHandler("broadcast", self.broadcast))

            # Handle answers and chat member updates
            self.application.add_handler(PollAnswerHandler(self.handle_answer))
            self.application.add_handler(ChatMemberHandler(self.track_chats, ChatMemberHandler.MY_CHAT_MEMBER))

            # Schedule cleanup and quiz jobs
            self.application.job_queue.run_repeating(
                self.scheduled_quiz,
                interval=1200,  # Every 20 minutes
                first=10
            )
            self.application.job_queue.run_repeating(
                self.scheduled_cleanup,
                interval=3600,  # Every hour
                first=300
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
        result = extract_status_change(update.my_chat_member)

        if result is None:
            return

        was_member, is_member = result

        # Handle chat type
        chat = update.effective_chat
        if chat.type in ["group", "supergroup"]:
            if not was_member and is_member:
                # Bot was added to a group
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

        🔥 Add me as an admin & let's make learning fun!"""

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            # Send first quiz after welcome
            await self.send_quiz(chat_id, context)
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
/broadcast – Send announcements"""

            help_text += "\n════════════════"
            await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await update.message.reply_text("Error showing help.")

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
        """Show user's personal stats"""
        try:
            user = update.message.from_user
            stats = self.quiz_manager.get_user_stats(user.id)

            stats_message = f"""📊 𝗤𝘂𝗶𝘇 𝗠𝗮𝘀𝘁𝗲𝗿 𝗣𝗲𝗿𝘀𝗼𝗻𝗮𝗹 𝗦𝘁𝗮𝘁𝘀
════════════════
👤 IIı {user.first_name} 🇮🇳 ıII

🎯 𝗣𝗲𝗿𝗳𝗼𝗿𝗺𝗮𝗻𝗰𝗲
• Total Quizzes: {stats['total_quizzes']}
• Correct Answers: {stats['correct_answers']}
• Success Rate: {stats['success_rate']}%
• Current Score: {stats['current_score']}

📈 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆
• Today: {stats['today_quizzes']} quizzes
• This Week: {stats['week_quizzes']} quizzes
• This Month: {stats['month_quizzes']} quizzes

Use /help to see all available commands! 🎮"""

            await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            await update.message.reply_text("Error retrieving your stats.")

    async def groupstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show comprehensive group performance stats - only works in groups"""
        try:
            chat = update.effective_chat

            # Check if command is used in a group
            if not chat.type.endswith('group'):
                await update.message.reply_text("This command only works in groups! 👥", parse_mode=ParseMode.MARKDOWN)
                return

            stats = self.quiz_manager.get_group_leaderboard(chat.id)

            if not stats['leaderboard']:
                await update.message.reply_text("No quiz participants in this group yet! Start taking quizzes to appear here! 🎯", parse_mode=ParseMode.MARKDOWN)
                return

            # Header with group analytics
            stats_message = f"""📊 𝗚𝗿𝗼𝘂𝗽 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀 - {chat.title}
════════════════

📈 𝗚𝗿𝗼𝘂𝗽 𝗣𝗲𝗿𝗳𝗼𝗿𝗺𝗮𝗻𝗰𝗲
• Total Quizzes: {stats['total_quizzes']}
• Correct Answers: {stats['total_correct']}
• Group Accuracy: {stats['group_accuracy']}%

👥 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆 𝗧𝗿𝗮𝗰𝗸𝗶𝗻𝗴
• Active Today: {stats['active_users']['today']} users
• Active This Week: {stats['active_users']['week']} users
• Active This Month: {stats['active_users']['month']} users
• Total Participants: {stats['active_users']['total']} users

🏆 𝗧𝗼𝗽 𝗣𝗲𝗿𝗳𝗼𝗿𝗺𝗲𝗿𝘀"""

            # Add top performers
            for rank, entry in enumerate(stats['leaderboard'][:5], 1):
                try:
                    user = await context.bot.get_chat(entry['user_id'])
                    username = user.first_name or user.username or "Anonymous"

                    stats_message += f"\n\n{rank}. {username}"
                    stats_message += f"\n   ✅ Total: {entry['total_attempts']} quizzes"
                    stats_message += f"\n   🎯 Correct: {entry['correct_answers']}"
                    stats_message += f"\n   📊 Accuracy: {entry['accuracy']}%"
                    stats_message += f"\n   🔥 Streak: {entry.get('current_streak', 0)}"
                    stats_message += f"\n   ⚡ Last Active: {entry['last_active']}"
                except Exception as e:
                    logger.error(f"Error getting user info for ID {entry['user_id']}: {e}")
                    continue

            stats_message += "\n\n📱 Real-time stats | Auto-updates every 20 min"
            await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error(f"Error getting group stats: {e}")
            await update.message.reply_text("Error retrieving group stats. Please try again.")

    async def leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show global leaderboard"""
        try:
            leaderboard = self.quiz_manager.get_leaderboard()

            if not leaderboard:
                await update.message.reply_text("No quiz participants yet! Be the first one to start! 🎯", parse_mode=ParseMode.MARKDOWN)
                return

            # Header
            leaderboard_text = "   🏆 All-Time Quiz Champions\n\n"

            # Get user info for each leaderboard entry
            for rank, entry in enumerate(leaderboard, 1):
                try:
                    # Get user info from Telegram
                    user = await context.bot.get_chat(entry['user_id'])
                    username = user.first_name or user.username or "Anonymous"

                    leaderboard_text += f"   🏅 {rank}. {username}\n"
                    leaderboard_text += f"      ✅ Attend: {entry['total_attempts']}\n"
                    leaderboard_text += f"      🎯 Correct: {entry['correct_answers']}\n"
                    leaderboard_text += f"      ❌ Wrong: {entry['wrong_answers']}\n"
                    leaderboard_text += f"      📊 Accuracy: {entry['accuracy']}%\n\n"
                except Exception as e:
                    logger.error(f"Error getting user info for ID {entry['user_id']}: {e}")
                    continue

            await update.message.reply_text(leaderboard_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error showing leaderboard: {e}")
            await update.message.reply_text("Error retrieving leaderboard.")

    async def allreload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Full bot restart - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Reload data
            self.quiz_manager.load_data()

            # Clear caches
            self.quiz_manager.get_random_question.cache_clear()
            self.quiz_manager.get_user_stats.cache_clear()

            await update.message.reply_text("✅ Bot data reloaded successfully!\n\n• Questions reloaded\n• Stats refreshed\n• Caches cleared", parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error(f"Error in allreload: {e}")
            await update.message.reply_text("❌ Error restarting bot.")

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

            # Prepare response message
            response = f"""📝 𝗤𝘂𝗶𝘇 𝗔𝗱𝗱𝗶𝘁𝗶𝗼𝗻 𝗥𝗲𝗽𝗼𝗿𝘁
════════════════
✅ Successfully added: {stats['added']} questions

❌ 𝗥𝗲𝗷𝗲𝗰𝘁𝗲𝗱:
• Duplicates: {stats['rejected']['duplicates']}
• Invalid Format: {stats['rejected']['invalid_format']}
• Invalid Options: {stats['rejected']['invalid_options']}"""

            if stats['errors']:
                response += "\n\n⚠️ 𝗘𝗿𝗿𝗼𝗿𝘀:"
                for error in stats['errors'][:5]:  # Show first 5 errors
                    response += f"\n• {error}"
                if len(stats['errors']) > 5:
                    response += f"\n• ...and {len(stats['errors']) - 5} more errors"

            await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error(f"Error in addquiz: {e}")
            await update.message.reply_text("❌ Error adding quiz.")

    async def globalstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show bot statistics - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            active_chats = self.quiz_manager.get_active_chats()
            total_users = len(self.quiz_manager.stats)
            total_groups = len(active_chats)

            # Calculate active users and groups today
            current_date = datetime.now().strftime('%Y-%m-%d')
            active_users_today = sum(
                1 for stats in self.quiz_manager.stats.values()
                if stats.get('last_quiz_date') == current_date
            )
            active_groups_today = sum(
                1 for chat_id in active_chats
                if any(
                    stats.get('last_quiz_date') == current_date
                    for stats in self.quiz_manager.stats.values()
                    if str(chat_id) in stats.get('groups', {})
                )
            )

            # Calculate quizzes over time periods
            today_quizzes = sum(
                stats['daily_activity'].get(current_date, {}).get('attempts', 0)
                for stats in self.quiz_manager.stats.values()
            )

            # Calculate this week's quizzes
            week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime('%Y-%m-%d')
            week_quizzes = sum(
                day_stats.get('attempts', 0)
                for stats in self.quiz_manager.stats.values()
                for date, day_stats in stats['daily_activity'].items()
                if date >= week_start
            )

            # Calculate this month's quizzes
            month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
            month_quizzes = sum(
                day_stats.get('attempts', 0)
                for stats in self.quiz_manager.stats.values()
                for date, day_stats in stats['daily_activity'].items()
                if date >= month_start
            )

            # Calculate all-time quizzes
            all_time_quizzes = sum(
                stats['total_quizzes']
                for stats in self.quiz_manager.stats.values()
            )

            stats_message = f"""🌟 𝗚𝗹𝗼𝗯𝗮𝗹 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀  
════════════════  
🎯 𝗖𝗼𝗺𝗺𝘂𝗻𝗶𝘁𝘆 𝗜𝗻𝘀𝗶𝗴𝗵𝘁𝘀
👥 Total Groups: {total_groups}  
👤 Total Users: {total_users}  
👥 Active Groups Today: {active_groups_today}  
👤 Active Users Today: {active_users_today}  

⚡ 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆 𝗧𝗿𝗮𝗰𝗸𝗲𝗿
📅 QuizzesSent Today: {today_quizzes}  
📆 This Week: {week_quizzes}  
📊 This Month: {month_quizzes}  
📌 All Time: {all_time_quizzes}  

🚀 Keep the competition going! Use /help to explore more commands! 🎮"""

            await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error(f"Error in globalstats: {e}")
            await update.message.reply_text("❌ Error retrieving global stats.")

    async def editquiz(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Edit existing quiz - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Get all questions
            questions = self.quiz_manager.get_all_questions()

            # Format for viewing
            questions_text = "📝 𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗤𝘂𝗲𝘀𝘁𝗶𝗼𝗻𝘀\n════════════════\n\n"

            for i, q in enumerate(questions):
                questions_text += f"{i+1}. {q['question']}\n"
                for j, opt in enumerate(q['options']):
                    questions_text += f"   {'✅' if j == q['correct_answer'] else '⭕'} {opt}\n"
                questions_text += "\n"

            # Split message if too long
            if len(questions_text) > 4000:
                for i in range(0, len(questions_text), 4000):
                    await update.message.reply_text(questions_text[i:i+4000], parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(questions_text, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error(f"Error in editquiz: {e}")
            await update.message.reply_text("❌ Error editing quiz.", parse_mode=ParseMode.MARKDOWN)

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

    async def is_developer(self, user_id: int) -> bool:
        """Check if user is a developer"""
        try:
            user = await self.application.bot.get_chat_member(user_id, user_id)
            return (user.user.username in ['CV_Owner', 'Ace_Clat'])
        except Exception as e:
            logger.error(f"Error checking developer status: {e}")
            return False

    async def _handle_dev_command_unauthorized(self, update: Update) -> None:
        """Handle unauthorized access to developer commands"""
        message = """🔒 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 𝗔𝗖𝗖𝗘𝗦𝗦 𝗢𝗡𝗟𝗬
════════════════
🚀 𝗥𝗲𝘀𝘁𝗿𝗶𝗰𝘁𝗲𝗱 𝗔𝗰𝗰𝗲𝘀𝘀
🔹 This command is exclusively available to the Developer & His Wife to maintain quiz integrity & security.

📌 𝗦𝘂𝗽𝗽𝗼𝗿𝘁 & ଇ𝗻𝗾𝘂𝗶𝗿𝗶𝗲𝘀
📩 Contact: @CV_Owner & His Wifu ❤️
💰 Paid Promotions: Up to 25K GC
📝 Contribute: Share your quiz ideas
⚠️ Report: Issues & bugs
💡 Suggest: Improvements & enhancements

✅ Thank you for your cooperation!
════════════════"""
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

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
    """Extract whether bot was added or removed."""
    status_change = chat_member_update.difference().get("status")
    if status_change is None:
        return None

    old_is_member = chat_member_update.old_chat_member.status in (
        "member", "administrator", "creator"
    )
    new_is_member = chat_member_update.new_chat_member.status in (
        "member", "administrator", "creator"
    )
    return old_is_member, new_is_member