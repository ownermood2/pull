    async def globalstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show comprehensive bot statistics - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Get global statistics with new tracking
            try:
                stats = self.quiz_manager.get_global_statistics()
                logger.info(f"Retrieved global stats: {stats}")
            except Exception as e:
                logger.error(f"Error getting statistics: {e}")
                raise

            stats_message = f"""📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀
════════════════
👥 𝗨𝘀𝗲𝗿𝘀 & 𝗚𝗿𝗼𝘂𝗽𝘀
• Total Users: {stats['users']['total']:,}
• Group Users: {stats['users']['group_users']:,}
• Private Users: {stats['users']['private_chat']:,}
• Active Today: {stats['users']['active_today']:,}

👥 𝗚𝗿𝗼𝘂𝗽 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆
• Total Groups: {stats['groups']['total']:,}
• Active Today: {stats['groups']['active_today']:,}
• Active Week: {stats['groups']['active_week']:,}

📈 𝗤𝘂𝗶𝘇 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆
• Today's Quizzes: {stats['quizzes']['today_attempts']:,}
• Week Quizzes: {stats['quizzes']['week_attempts']:,}
• Total Attempts: {stats['quizzes']['total_attempts']:,}
• Correct Answers: {stats['quizzes']['correct_answers']:,}
• Success Rate: {stats['performance']['success_rate']}%

⚡ 𝗥𝗲𝗮𝗹-𝘁𝗶𝗺𝗲 𝗠𝗲𝘁𝗿𝗶𝗰𝘀
• Questions Available: {stats['performance']['questions_available']:,}
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