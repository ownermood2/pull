import json
import random
import os
import logging
import traceback
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from functools import lru_cache

logger = logging.getLogger(__name__)

class QuizManager:
    def __init__(self):
        """Initialize the quiz manager with proper data structures and caching"""
        self.questions_file = "data/questions.json"
        self.scores_file = "data/scores.json"
        self.active_chats_file = "data/active_chats.json"
        self.stats_file = "data/user_stats.json"
        self._initialize_files()
        self.load_data()
        self._last_save = datetime.now()
        self._save_interval = timedelta(minutes=5)
        self._cached_questions = None
        self._cached_leaderboard = None
        self._leaderboard_cache_time = None
        self._cache_duration = timedelta(minutes=5)

    def _initialize_files(self):
        """Initialize data files with proper error handling"""
        try:
            os.makedirs("data", exist_ok=True)
            default_files = {
                self.questions_file: [],
                self.scores_file: {},
                self.active_chats_file: [],
                self.stats_file: {}
            }
            for file_path, default_data in default_files.items():
                if not os.path.exists(file_path):
                    with open(file_path, 'w') as f:
                        json.dump(default_data, f)
        except Exception as e:
            logger.error(f"Error initializing files: {e}")
            raise

    def load_data(self):
        """Load all data with proper error handling"""
        try:
            with open(self.questions_file, 'r') as f:
                self.questions = json.load(f)
            with open(self.scores_file, 'r') as f:
                self.scores = json.load(f)
            with open(self.active_chats_file, 'r') as f:
                self.active_chats = json.load(f)
            with open(self.stats_file, 'r') as f:
                self.stats = json.load(f)
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            raise

    def save_data(self):
        """Save data with throttling to prevent excessive writes"""
        current_time = datetime.now()
        if current_time - self._last_save < self._save_interval:
            return

        try:
            with open(self.questions_file, 'w') as f:
                json.dump(self.questions, f)
            with open(self.scores_file, 'w') as f:
                json.dump(self.scores, f)
            with open(self.active_chats_file, 'w') as f:
                json.dump(self.active_chats, f)
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f)
            self._last_save = current_time
        except Exception as e:
            logger.error(f"Error saving data: {e}")
            raise

    def _init_user_stats(self, user_id: str) -> None:
        """Initialize stats for a new user"""
        self.stats[user_id] = {
            'total_quizzes': 0,
            'correct_answers': 0,
            'current_streak': 0,
            'longest_streak': 0,
            'last_correct_date': None,
            'category_scores': {},
            'daily_activity': {},
            'last_quiz_date': None,
            'groups': {}
        }

    @lru_cache(maxsize=100)
    def get_user_stats(self, user_id: int) -> Dict:
        """Get comprehensive stats for a user with caching"""
        try:
            user_id = str(user_id)
            if user_id not in self.stats:
                self._init_user_stats(user_id)
                self.save_data()

            stats = self.stats[user_id]
            current_date = datetime.now()

            # Synchronize score with correct answers and fix any inconsistencies
            score = self.scores.get(user_id, 0)
            if score > 0:
                stats['total_quizzes'] = max(stats['total_quizzes'], score)
                stats['correct_answers'] = score
                self.save_data()
                logger.info(f"Synchronized stats for user {user_id}: score={score}, total_quizzes={stats['total_quizzes']}")

            # Calculate activity stats
            today = current_date.strftime('%Y-%m-%d')
            today_stats = stats['daily_activity'].get(today, {'attempts': 0})

            # Calculate this week's stats
            week_start = (current_date - timedelta(days=current_date.weekday())).strftime('%Y-%m-%d')
            week_quizzes = sum(
                day_stats['attempts']
                for date, day_stats in stats['daily_activity'].items()
                if date >= week_start
            )

            # Calculate this month's stats
            month_start = current_date.replace(day=1).strftime('%Y-%m-%d')
            month_quizzes = sum(
                day_stats['attempts']
                for date, day_stats in stats['daily_activity'].items()
                if date >= month_start
            )

            # Calculate success rate
            success_rate = (
                (stats['correct_answers'] / stats['total_quizzes'] * 100)
                if stats['total_quizzes'] > 0
                else 0.0
            )

            # Get category mastery
            category_master = None
            if stats['category_scores']:
                best_category = max(stats['category_scores'].items(), key=lambda x: x[1])
                if best_category[1] >= 10:  # Threshold for mastery
                    category_master = best_category[0]

            return {
                'total_quizzes': stats['total_quizzes'],
                'correct_answers': stats['correct_answers'],
                'success_rate': round(success_rate, 1),
                'current_score': stats['correct_answers'],
                'today_quizzes': today_stats['attempts'],
                'week_quizzes': week_quizzes,
                'month_quizzes': month_quizzes,
                'current_streak': stats['current_streak'],
                'longest_streak': stats['longest_streak'],
                'category_master': category_master
            }
        except Exception as e:
            logger.error(f"Error getting user stats for {user_id}: {str(e)}\n{traceback.format_exc()}")
            # Return default stats in case of error
            return {
                'total_quizzes': 0,
                'correct_answers': 0,
                'success_rate': 0.0,
                'current_score': 0,
                'today_quizzes': 0,
                'week_quizzes': 0,
                'month_quizzes': 0,
                'current_streak': 0,
                'longest_streak': 0,
                'category_master': None
            }

    def get_group_leaderboard(self, chat_id: int) -> Dict:
        """Get group-specific leaderboard with detailed analytics"""
        chat_id_str = str(chat_id)
        current_date = datetime.now()
        today = current_date.strftime('%Y-%m-%d')
        week_start = (current_date - timedelta(days=current_date.weekday())).strftime('%Y-%m-%d')
        month_start = current_date.replace(day=1).strftime('%Y-%m-%d')

        # Initialize counters and sets
        total_group_quizzes = 0
        total_correct_answers = 0
        active_users = {
            'today': set(),
            'week': set(),
            'month': set(),
            'total': set()
        }
        leaderboard = []

        # Process user stats
        for user_id, stats in self.stats.items():
            if chat_id_str in stats.get('groups', {}):
                group_stats = stats['groups'][chat_id_str]
                active_users['total'].add(user_id)

                # Update activity counters
                last_activity = group_stats.get('last_activity_date')
                if last_activity:
                    if last_activity == today:
                        active_users['today'].add(user_id)
                    if last_activity >= week_start:
                        active_users['week'].add(user_id)
                    if last_activity >= month_start:
                        active_users['month'].add(user_id)

                # Calculate user statistics
                user_total_attempts = group_stats.get('total_quizzes', 0)
                user_correct_answers = group_stats.get('correct_answers', 0)
                total_group_quizzes += user_total_attempts
                total_correct_answers += user_correct_answers

                # Get daily activity stats
                daily_stats = group_stats.get('daily_activity', {})
                today_stats = daily_stats.get(today, {'attempts': 0, 'correct': 0})

                leaderboard.append({
                    'user_id': int(user_id),
                    'total_attempts': user_total_attempts,
                    'correct_answers': user_correct_answers,
                    'wrong_answers': user_total_attempts - user_correct_answers,
                    'accuracy': round((user_correct_answers / user_total_attempts * 100) if user_total_attempts > 0 else 0, 1),
                    'score': group_stats.get('score', 0),
                    'current_streak': group_stats.get('current_streak', 0),
                    'longest_streak': group_stats.get('longest_streak', 0),
                    'today_attempts': today_stats['attempts'],
                    'today_correct': today_stats['correct'],
                    'last_active': group_stats.get('last_activity_date', 'Never')
                })

        # Sort leaderboard by score and accuracy
        leaderboard.sort(key=lambda x: (x['score'], x['accuracy']), reverse=True)
        group_accuracy = (total_correct_answers / total_group_quizzes * 100) if total_group_quizzes > 0 else 0

        return {
            'total_quizzes': total_group_quizzes,
            'total_correct': total_correct_answers,
            'group_accuracy': round(group_accuracy, 1),
            'active_users': {
                'today': len(active_users['today']),
                'week': len(active_users['week']),
                'month': len(active_users['month']),
                'total': len(active_users['total'])
            },
            'leaderboard': leaderboard[:10]  # Top 10 performers
        }

    def record_group_attempt(self, user_id: int, chat_id: int, is_correct: bool) -> None:
        """Record a quiz attempt for a user in a specific group with timestamp"""
        try:
            user_id = str(user_id)
            chat_id = str(chat_id)
            current_date = datetime.now().strftime('%Y-%m-%d')

            if user_id not in self.stats:
                self._init_user_stats(user_id)

            stats = self.stats[user_id]
            if 'groups' not in stats:
                stats['groups'] = {}

            if chat_id not in stats['groups']:
                stats['groups'][chat_id] = {
                    'total_quizzes': 0,
                    'correct_answers': 0,
                    'score': 0,
                    'last_activity_date': None,
                    'daily_activity': {},
                    'current_streak': 0,
                    'longest_streak': 0,
                    'last_correct_date': None
                }

            group_stats = stats['groups'][chat_id]
            group_stats['total_quizzes'] += 1
            group_stats['last_activity_date'] = current_date

            # Update daily activity
            if current_date not in group_stats['daily_activity']:
                group_stats['daily_activity'][current_date] = {'attempts': 0, 'correct': 0}
            group_stats['daily_activity'][current_date]['attempts'] += 1

            if is_correct:
                group_stats['correct_answers'] += 1
                group_stats['score'] += 1
                group_stats['daily_activity'][current_date]['correct'] += 1

                # Update streak
                if group_stats.get('last_correct_date') == (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'):
                    group_stats['current_streak'] += 1
                else:
                    group_stats['current_streak'] = 1

                group_stats['longest_streak'] = max(group_stats['current_streak'], group_stats['longest_streak'])
                group_stats['last_correct_date'] = current_date
            else:
                group_stats['current_streak'] = 0

            self.save_data()
            logger.info(f"Updated group stats for user {user_id} in group {chat_id}")

        except Exception as e:
            logger.error(f"Error recording group attempt: {e}")
            raise

    @lru_cache(maxsize=1)
    def get_random_question(self) -> Optional[Dict[str, Any]]:
        """Get a random question with caching"""
        if not self.questions:
            return None
        return random.choice(self.questions)

    def get_leaderboard(self) -> List[Dict]:
        """Get global leaderboard with caching"""
        current_time = datetime.now()
        if (self._cached_leaderboard is None or
            self._leaderboard_cache_time is None or
            current_time - self._leaderboard_cache_time > self._cache_duration):

            leaderboard = []
            for user_id, stats in self.stats.items():
                total_attempts = stats['total_quizzes']
                correct_answers = stats['correct_answers']
                accuracy = (correct_answers / total_attempts * 100) if total_attempts > 0 else 0

                leaderboard.append({
                    'user_id': int(user_id),
                    'total_attempts': total_attempts,
                    'correct_answers': correct_answers,
                    'wrong_answers': total_attempts - correct_answers,
                    'accuracy': round(accuracy, 1),
                    'score': self.get_score(int(user_id))
                })

            leaderboard.sort(key=lambda x: x['score'], reverse=True)
            self._cached_leaderboard = leaderboard[:10]
            self._leaderboard_cache_time = current_time

        return self._cached_leaderboard

    def record_attempt(self, user_id: int, is_correct: bool, category: str = None):
        """Record a quiz attempt for a user"""
        user_id = str(user_id)
        current_date = datetime.now().strftime('%Y-%m-%d')

        if user_id not in self.stats:
            self._init_user_stats(user_id)

        stats = self.stats[user_id]
        stats['total_quizzes'] += 1
        stats['last_quiz_date'] = current_date

        if is_correct:
            stats['correct_answers'] += 1

            # Update streak
            if stats.get('last_correct_date') == (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'):
                stats['current_streak'] += 1
            else:
                stats['current_streak'] = 1

            stats['longest_streak'] = max(stats['current_streak'], stats['longest_streak'])
            stats['last_correct_date'] = current_date

            if category:
                if category not in stats['category_scores']:
                    stats['category_scores'][category] = 0
                stats['category_scores'][category] += 1
        else:
            stats['current_streak'] = 0

        # Update daily activity
        if current_date not in stats['daily_activity']:
            stats['daily_activity'][current_date] = {'attempts': 0, 'correct': 0}
        stats['daily_activity'][current_date]['attempts'] += 1
        if is_correct:
            stats['daily_activity'][current_date]['correct'] += 1

        self.save_data()

    def add_questions(self, questions_data: List[Dict]) -> Dict:
        """Add multiple questions with validation and duplicate detection

        Args:
            questions_data: List of question dictionaries with format:
                {
                    'question': str,
                    'options': List[str],
                    'correct_answer': int
                }

        Returns:
            Dict with stats about added/rejected questions
        """
        stats = {
            'added': 0,
            'rejected': {
                'duplicates': 0,
                'invalid_format': 0,
                'invalid_options': 0
            },
            'errors': []
        }

        if len(questions_data) > 500:
            stats['errors'].append("Maximum 500 questions allowed at once")
            return stats

        # Create a set of existing questions for duplicate checking
        existing_questions = {q['question'].lower().strip() for q in self.questions}

        for question_data in questions_data:
            try:
                # Basic format validation
                if not all(key in question_data for key in ['question', 'options', 'correct_answer']):
                    stats['rejected']['invalid_format'] += 1
                    stats['errors'].append(f"Invalid format for question: {question_data.get('question', 'Unknown')}")
                    continue

                question = question_data['question'].strip()
                options = [opt.strip() for opt in question_data['options']]
                correct_answer = question_data['correct_answer']

                # Validate question text
                if not question or len(question) < 5:
                    stats['rejected']['invalid_format'] += 1
                    stats['errors'].append(f"Question text too short: {question}")
                    continue

                # Check for duplicates
                if question.lower() in existing_questions:
                    stats['rejected']['duplicates'] += 1
                    stats['errors'].append(f"Duplicate question: {question}")
                    continue

                # Validate options
                if len(options) != 4 or not all(opt for opt in options):
                    stats['rejected']['invalid_options'] += 1
                    stats['errors'].append(f"Invalid options for question: {question}")
                    continue

                # Validate correct answer index
                if not isinstance(correct_answer, int) or not (0 <= correct_answer < 4):
                    stats['rejected']['invalid_format'] += 1
                    stats['errors'].append(f"Invalid correct answer index for question: {question}")
                    continue

                # Add valid question
                self.questions.append({
                    'question': question,
                    'options': options,
                    'correct_answer': correct_answer
                })
                existing_questions.add(question.lower())
                stats['added'] += 1

            except Exception as e:
                logger.error(f"Error processing question: {str(e)}")
                stats['errors'].append(f"Unexpected error: {str(e)}")

        if stats['added'] > 0:
            self.save_data()

        return stats

    def delete_question(self, index: int):
        if 0 <= index < len(self.questions):
            self.questions.pop(index)
            self.save_data()

    def get_all_questions(self) -> List[Dict]:
        return self.questions

    def increment_score(self, user_id: int):
        """Increment user's score and synchronize with statistics"""
        user_id = str(user_id)
        if user_id not in self.stats:
            self._init_user_stats(user_id)

        # Initialize score if needed
        if user_id not in self.scores:
            self.scores[user_id] = 0

        # Increment score and synchronize with stats
        self.scores[user_id] += 1
        stats = self.stats[user_id]
        stats['correct_answers'] = self.scores[user_id]
        stats['total_quizzes'] = max(stats['total_quizzes'] + 1, stats['correct_answers'])

        # Record the attempt after synchronizing
        self.record_attempt(user_id, True)
        self.save_data()

    def get_score(self, user_id: int) -> int:
        return self.scores.get(str(user_id), 0)

    def add_active_chat(self, chat_id: int):
        if chat_id not in self.active_chats:
            self.active_chats.append(chat_id)
            self.save_data()

    def remove_active_chat(self, chat_id: int):
        if chat_id in self.active_chats:
            self.active_chats.remove(chat_id)
            self.save_data()

    def get_active_chats(self) -> List[int]:
        return self.active_chats