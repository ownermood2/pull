    async def globalstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show comprehensive bot statistics - Developer only"""
        try:
            if not await self.is_developer(update.message.from_user.id):
                await self._handle_dev_command_unauthorized(update)
                return

            # Get basic stats with error handling
            try:
                stats = self.quiz_manager.get_global_statistics()
                if not stats:
                    await update.message.reply_text("❌ Error retrieving statistics.")
                    return

                # Format the statistics message
                stats_message = f"""📊 𝗚𝗹𝗼𝗯𝗮𝗹 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀 𝗥𝗲𝗽𝗼𝗿𝘁
════════════════
👤 𝗨𝘀𝗲𝗿 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆
• Total Users: {stats['users']['total']:,}
• Active Today: {stats['users']['active_today']:,}
• Active This Week: {stats['users']['active_week']:,}
• Active This Month: {stats['users']['active_month']:,}
• Private Chat Users: {stats['users']['private_chat']:,}

👥 𝗚𝗿𝗼𝘂𝗽 𝗔𝗰𝘁𝗶𝘃𝗶𝘁𝘆
• Total Groups: {stats['groups']['total']:,}
• Active Today: {stats['groups']['active_today']:,}
• Active This Week: {stats['groups']['active_week']:,}
• Active This Month: {stats['groups']['active_month']:,}

📈 𝗤𝘂𝗶𝘇 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀
• Total Attempts: {stats['quizzes']['total_attempts']:,}
• Correct Answers: {stats['quizzes']['correct_answers']:,}
• Today's Attempts: {stats['quizzes']['today_attempts']:,}
• This Week: {stats['quizzes']['week_attempts']:,}

⚡ 𝗣𝗲𝗿𝗳𝗼𝗿𝗺𝗮𝗻𝗰𝗲
• Success Rate: {stats['performance']['success_rate']}%
• Average Score: {stats['performance']['avg_score']}
• Available Questions: {stats['performance']['questions_available']:,}
════════════════
🔄 Real-time stats | Auto-updates"""

                await update.message.reply_text(
                    stats_message,
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"Displayed global stats to developer {update.effective_user.id}")

            except Exception as e:
                logger.error(f"Error processing statistics: {e}\n{traceback.format_exc()}")
                raise

        except Exception as e:
            logger.error(f"Error in globalstats: {e}\n{traceback.format_exc()}")
            await update.message.reply_text("❌ Error retrieving global statistics. Please try again.")