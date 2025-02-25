    async def globalstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Enhanced global statistics with real-time tracking"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Ensure stats are up to date
            self.quiz_manager.update_all_stats()
            
            # Get basic stats
            active_chats = self.quiz_manager.get_active_chats()
            total_users = len(self.quiz_manager.stats)
            total_groups = len(active_chats)
            
            # Calculate time-based metrics
            current_date = datetime.now().strftime('%Y-%m-%d')
            week_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')

            # Calculate active users
            today_active_users = sum(
                1 for stats in self.quiz_manager.stats.values()
                if stats.get('last_activity_date') == current_date
            )
            week_active_users = sum(
                1 for stats in self.quiz_manager.stats.values()
                if stats.get('last_activity_date', '1970-01-01') >= week_start
            )
            month_active_users = sum(
                1 for stats in self.quiz_manager.stats.values()
                if stats.get('last_activity_date', '1970-01-01') >= month_start
            )

            # Calculate active groups
            active_groups_today = len([
                c for c in active_chats 
                if self.quiz_manager.get_group_last_activity(c) == current_date
            ])
            active_groups_week = len([
                c for c in active_chats 
                if self.quiz_manager.get_group_last_activity(c) >= week_start
            ])

            # Calculate quiz statistics
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

            # Calculate participation rates
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

            # Calculate private chat stats
            private_chat_users = sum(
                1 for user_id, stats in self.quiz_manager.stats.items()
                if str(user_id) in [str(c) for c in active_chats]
            )
            private_chat_active = sum(
                1 for user_id, stats in self.quiz_manager.stats.items()
                if str(user_id) in [str(c) for c in active_chats] and
                stats.get('last_activity_date') == current_date
            )

            stats_message = f"""📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀
════════════════
👥 𝗨𝘀𝗲𝗿𝘀 & 𝗚𝗿𝗼𝘂𝗽𝘀
• Total Users: {total_users}
• Total Groups: {total_groups}
• Active Today: {today_active_users}
• Active This Week: {week_active_users}
• Monthly Active: {month_active_users}

📈 𝗚𝗿𝗼𝘂𝗽 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆
• Active Today: {active_groups_today}
• Active This Week: {active_groups_week}
• Private Chats: {private_chat_users}
• Private Active Today: {private_chat_active}

🎯 𝗤𝘂𝗶𝘇 𝗦𝘁𝗮𝘁𝘀
• Today's Quizzes: {today_quizzes}
• This Week: {week_quizzes}
• Total Attempts: {total_attempts}
• Correct Answers: {correct_answers}
• Success Rate: {success_rate}%

⚡ 𝗥𝗲𝗮𝗹-𝘁𝗶𝗺𝗲 𝗠𝗲𝘁𝗿𝗶𝗰𝘀
• Questions Available: {len(self.quiz_manager.questions)}
• Current Active Groups: {active_groups_today}
• New Users Today: {len([u for u, s in self.quiz_manager.stats.items() if s.get('join_date') == current_date])}
════════════════"""

            try:
                await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)
                logger.info(f"Global stats shown to developer {update.effective_user.id}")
            except Exception as e:
                logger.error(f"Failed to send stats with markdown: {e}")
                # Fallback to plain text if markdown fails
                plain_text = stats_message.replace('𝗕', 'B').replace('𝗨', 'U').replace('𝗚', 'G').replace('𝗤', 'Q').replace('𝗔', 'A').replace('𝗥', 'R').replace('𝗠', 'M').replace('═', '=').replace('•', '*')
                await update.message.reply_text(plain_text)

        except Exception as e:
            logger.error(f"Error in globalstats: {e}\n{traceback.format_exc()}")
            await update.message.reply_text("❌ Error retrieving global statistics. Please try again.")