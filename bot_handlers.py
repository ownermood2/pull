import os
import logging
import traceback
from datetime import datetime, timedelta
from collections import defaultdict
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
        self.command_cooldowns = defaultdict(lambda: defaultdict(int))
        self.COOLDOWN_PERIOD = 3  # seconds between commands

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
            self.application.add_handler(CommandHandler("allreload", self.allreload))
            self.application.add_handler(CommandHandler("addquiz", self.addquiz))
            self.application.add_handler(CommandHandler("globalstats", self.globalstats))
            self.application.add_handler(CommandHandler("editquiz", self.editquiz))
            self.application.add_handler(CommandHandler("broadcast", self.broadcast))
            self.application.add_handler(PollAnswerHandler(self.handle_answer))

            # Schedule quiz every 20 minutes (1200 seconds)
            self.application.job_queue.run_repeating(
                self.scheduled_quiz,
                interval=1200,
                first=10
            )

            # Schedule cleanup of old poll data
            self.application.job_queue.run_repeating(
                self.cleanup_old_polls,
                interval=3600,  # Every hour
                first=300  # Start after 5 minutes
            )

            # Initialize and start polling
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            return self

        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise

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

    async def send_quiz(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a quiz to a specific chat using native Telegram quiz format"""
        try:
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

        except Exception as e:
            logger.error(f"Error sending quiz: {str(e)}\n{traceback.format_exc()}")
            await context.bot.send_message(chat_id=chat_id, text="Error sending quiz.")

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
            self.quiz_manager.add_active_chat(chat_id)

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
            help_text = """🎯 𝗤𝘂𝗶𝘇 𝗠𝗮𝘀𝘁𝗲𝗿 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 🎯   
════════════════
📝 𝗚𝗘𝗡𝗘𝗥𝗔𝗟 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦  
/start – Begin your quiz journey  
/help – Available commands  
/category – View Topics
/quiz – Try a quiz demo  
            
📊 𝗦𝗧𝗔𝗧𝗦 & 𝗟𝗘𝗔𝗗𝗘𝗥𝗕𝗢𝗔𝗥𝗗  
/mystats - Your Performance 
/groupstats – Your group performance   
/leaderboard – See champions  
            
🔒 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦  
/allreload – Full bot restart  
/addquiz – Add new questions
/globalstats – Bot stats   
/editquiz – Modify  quizzes  
/broadcast –  Send announcements  
════════════════
💡 Need Help? Use /help to explore all features! 🌟"""

            await update.message.reply_text(help_text)
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

            await update.message.reply_text(category_text)
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

            await update.message.reply_text(stats_message)
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            await update.message.reply_text("Error retrieving your stats.")

    async def groupstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show comprehensive group performance stats - only works in groups"""
        try:
            chat = update.effective_chat

            # Check if command is used in a group
            if not chat.type.endswith('group'):
                await update.message.reply_text("This command only works in groups! 👥")
                return

            stats = self.quiz_manager.get_group_leaderboard(chat.id)

            if not stats['leaderboard']:
                await update.message.reply_text("No quiz participants in this group yet! Start taking quizzes to appear here! 🎯")
                return

            # Header with group analytics
            stats_message = f"""📊 𝗚𝗿𝗼𝘂𝗽 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀 - {chat.title}
════════════════
            
📈 𝗚𝗿𝗼𝘂𝗽 𝗣𝗲𝗿𝗳𝗼𝗿𝗺𝗮𝗻𝗰𝗲
• Total Quizzes: {stats['total_quizzes']}
• Correct Answers: {stats['total_correct']}
• Group Accuracy: {stats['group_accuracy']}%
            
👥 𝗔𝗰𝘁𝗶𝘃𝗲 𝗨𝘀𝗲𝗿𝘀
• Today: {stats['active_users']['today']}
• This Week: {stats['active_users']['week']}
• This Month: {stats['active_users']['month']}
• Total Members: {stats['active_users']['total']}
            
🏆 𝗚𝗿𝗼𝘂𝗽 𝗖𝗵𝗮𝗺𝗽𝗶𝗼𝗻𝘀"""

            # Add user entries
            for rank, entry in enumerate(stats['leaderboard'], 1):
                try:
                    # Get user info from Telegram
                    user = await context.bot.get_chat(entry['user_id'])
                    username = user.first_name or user.username or "Anonymous"

                    stats_message += f"\n\n   🏅 {rank}. {username}"
                    stats_message += f"\n      ✅ Attend: {entry['total_attempts']}"
                    stats_message += f"\n      🎯 Correct: {entry['correct_answers']}"
                    stats_message += f"\n      ❌ Wrong: {entry['wrong_answers']}"
                    stats_message += f"\n      📊 Accuracy: {entry['accuracy']}%"
                    stats_message += f"\n      📅 Last Active: {entry['last_active']}"
                except Exception as e:
                    logger.error(f"Error getting user info for ID {entry['user_id']}: {e}")
                    continue

            await update.message.reply_text(stats_message)
        except Exception as e:
            logger.error(f"Error getting group stats: {e}")
            await update.message.reply_text("Error retrieving group stats.")

    async def leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show global leaderboard"""
        try:
            leaderboard = self.quiz_manager.get_leaderboard()

            if not leaderboard:
                await update.message.reply_text("No quiz participants yet! Be the first one to start! 🎯")
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

            await update.message.reply_text(leaderboard_text)
        except Exception as e:
            logger.error(f"Error showing leaderboard: {e}")
            await update.message.reply_text("Error retrieving leaderboard.")

    async def allreload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Full bot restart - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await update.message.reply_text("This command is for developers only.")
                return

            # Reload data
            self.quiz_manager.load_data()

            # Clear caches
            self.quiz_manager.get_random_question.cache_clear()
            self.quiz_manager.get_user_stats.cache_clear()

            await update.message.reply_text("✅ Bot data reloaded successfully!\n\n• Questions reloaded\n• Stats refreshed\n• Caches cleared")

        except Exception as e:
            logger.error(f"Error in allreload: {e}")
            await update.message.reply_text("❌ Error restarting bot.")

    async def addquiz(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Add new quiz(zes) - Developer only
        Format for single question:
        /addquiz question | option1 | option2 | option3 | option4 | correct_number

        Format for multiple questions:
        /addquiz
        Q: question1
        1. option1
        2. option2
        3. option3
        4. option4
        A: correct_number

        Q: question2
        ...etc
        """
        try:
            if not await self.is_developer(update.message.from_user.id):
                await update.message.reply_text("This command is for developers only.")
                return

            # Extract message content
            content = update.message.text.split(" ", 1)
            if len(content) < 2:
                await update.message.reply_text(
                    "❌ Please provide questions in the correct format.\n\n"
                    "For single question:\n"
                    "/addquiz question | option1 | option2 | option3 | option4 | correct_number\n\n"
                    "For multiple questions:\n"
                    "/addquiz\n"
                    "Q: What is the capital of France?\n"
                    "1. London\n"
                    "2. Paris\n"
                    "3. Berlin\n"
                    "4. Madrid\n"
                    "A: 2\n\n"
                    "Q: Next question...\n"
                    "..."
                )
                return

            questions_data = []
            message_text = content[1].strip()

            # Check if it's the single question format (using |)
            if "|" in message_text:
                parts = message_text.split("|")
                if len(parts) != 6:
                    await update.message.reply_text("❌ Invalid format for single question")
                    return

                questions_data.append({
                    'question': parts[0].strip(),
                    'options': [p.strip() for p in parts[1:5]],
                    'correct_answer': int(parts[5].strip()) - 1
                })
            else:
                # Multiple questions format
                current_question = None
                current_options = []

                for line in message_text.split('\n'):
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith('Q:'):
                        # Save previous question if exists
                        if current_question is not None and len(current_options) == 4:
                            questions_data.append({
                                'question': current_question,
                                'options': current_options,
                                'correct_answer': None  # Will be set when we find 'A:'
                            })
                        current_question = line[2:].strip()
                        current_options = []
                    elif line.startswith(('1.', '2.', '3.', '4.')):
                        if current_question is not None:
                            current_options.append(line[2:].strip())
                    elif line.startswith('A:'):
                        if current_question is not None and len(current_options) == 4:
                            try:
                                correct_answer = int(line[2:].strip()) - 1
                                if 0 <= correct_answer < 4:
                                    questions_data.append({
                                        'question': current_question,
                                        'options': current_options,
                                        'correct_answer': correct_answer
                                    })
                            except ValueError:
                                pass
                        current_question = None
                        current_options = []

            if not questions_data:
                await update.message.reply_text(
                    "❌ No valid questions found in the input.\n"
                    "Please check the format and try again."
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

            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Error in addquiz: {e}")
            await update.message.reply_text("❌ Error adding quiz.")

    async def globalstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show bot statistics - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await update.message.reply_text("This command is for developers only.")
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
📅 Quizzes Sent Today: {today_quizzes}  
📆 This Week: {week_quizzes}  
📊 This Month: {month_quizzes}  
📌 All Time: {all_time_quizzes}  
            
🚀 Keep the competition going! Use /help to explore more commands! 🎮"""

            await update.message.reply_text(stats_message)

        except Exception as e:
            logger.error(f"Error in globalstats: {e}")
            await update.message.reply_text("❌ Error retrieving global stats.")

    async def editquiz(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Edit existing quiz - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await update.message.reply_text("This command is for developers only.")
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
                    await update.message.reply_text(questions_text[i:i+4000])
            else:
                await update.message.reply_text(questions_text)

        except Exception as e:
            logger.error(f"Error in editquiz: {e}")
            await update.message.reply_text("❌ Error editing quiz.")

    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send announcements - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await update.message.reply_text("This command is for developers only.")
                return

            # Get message to broadcast
            try:
                message = update.message.text.split(" ", 1)[1]
            except IndexError:
                await update.message.reply_text(
                    "❌ Please provide a message to broadcast.\n"
                    "Format: /broadcast Your message here"
                )
                return

            active_chats = self.quiz_manager.get_active_chats()
            success_count = 0
            fail_count = 0

            # Send to all active chats
            for chat_id in active_chats:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"📢 𝗔𝗻𝗻𝗼𝘂𝗻𝗰𝗲𝗺𝗲𝗻𝘁\n════════════════\n\n{message}"
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send broadcast to {chat_id}: {e}")
                    fail_count += 1

            await update.message.reply_text(
                f"📢 Broadcast Results:\n"
                f"✅ Successfully sent to: {success_count} chats\n"
                f"❌ Failed to send to: {fail_count} chats"
            )

        except Exception as e:
            logger.error(f"Error in broadcast: {e}")
            await update.message.reply_text("❌ Error sending broadcast.")

    async def is_developer(self, user_id: int) -> bool:
        """Check if user is a developer"""
        # List of developer user IDs
        developer_ids = [7653153066]  # Added the user from logs as developer
        return user_id in developer_ids

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
        bot = TelegramQuizBot(quiz_manager)
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_TOKEN environment variable is required")
        await bot.initialize(token)
        return bot
    except Exception as e:
        logger.error(f"Failed to setup Telegram bot: {e}")
        raise