import json
import random
import os
from typing import List, Dict
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class QuizManager:
    def __init__(self):
        self.questions_file = "data/questions.json"
        self.scores_file = "data/scores.json"
        self.active_chats_file = "data/active_chats.json"
        self.stats_file = "data/user_stats.json"
        self._initialize_files()
        self.load_data()

    def _initialize_files(self):
        os.makedirs("data", exist_ok=True)

        # Initialize questions file
        if not os.path.exists(self.questions_file):
            with open(self.questions_file, 'w') as f:
                json.dump([], f)

        # Initialize scores file
        if not os.path.exists(self.scores_file):
            with open(self.scores_file, 'w') as f:
                json.dump({}, f)

        # Initialize active chats file
        if not os.path.exists(self.active_chats_file):
            with open(self.active_chats_file, 'w') as f:
                json.dump([], f)

        # Initialize stats file
        if not os.path.exists(self.stats_file):
            with open(self.stats_file, 'w') as f:
                json.dump({}, f)

    def load_data(self):
        with open(self.questions_file, 'r') as f:
            self.questions = json.load(f)
        with open(self.scores_file, 'r') as f:
            self.scores = json.load(f)
        with open(self.active_chats_file, 'r') as f:
            self.active_chats = json.load(f)
        with open(self.stats_file, 'r') as f:
            self.stats = json.load(f)

    def save_data(self):
        with open(self.questions_file, 'w') as f:
            json.dump(self.questions, f)
        with open(self.scores_file, 'w') as f:
            json.dump(self.scores, f)
        with open(self.active_chats_file, 'w') as f:
            json.dump(self.active_chats, f)
        with open(self.stats_file, 'w') as f:
            json.dump(self.stats, f)

    def _init_user_stats(self, user_id: str):
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
            'groups': {} #Added to support group stats
        }

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
            if stats['last_correct_date'] == (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'):
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

    def get_user_stats(self, user_id: int) -> Dict:
        """Get comprehensive stats for a user"""
        user_id = str(user_id)
        if user_id not in self.stats:
            self._init_user_stats(user_id)
            self.save_data()

        stats = self.stats[user_id]
        current_date = datetime.now()

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
            'current_score': self.get_score(int(user_id)),
            'today_quizzes': today_stats['attempts'],
            'week_quizzes': week_quizzes,
            'month_quizzes': month_quizzes,
            'current_streak': stats['current_streak'],
            'longest_streak': stats['longest_streak'],
            'category_master': category_master
        }

    def get_group_leaderboard(self, chat_id: int) -> Dict:
        """Get group-specific leaderboard with detailed analytics"""
        leaderboard = []
        chat_id_str = str(chat_id)
        total_group_quizzes = 0
        total_correct_answers = 0
        active_users_today = set()
        active_users_week = set()
        active_users_month = set()
        current_date = datetime.now()
        today = current_date.strftime('%Y-%m-%d')
        week_start = (current_date - timedelta(days=current_date.weekday())).strftime('%Y-%m-%d')
        month_start = current_date.replace(day=1).strftime('%Y-%m-%d')

        # Filter stats for users who have participated in this group
        for user_id, stats in self.stats.items():
            if chat_id_str in stats.get('groups', {}):
                group_stats = stats['groups'][chat_id_str]
                user_total_attempts = group_stats.get('total_quizzes', 0)
                user_correct_answers = group_stats.get('correct_answers', 0)
                user_wrong_answers = user_total_attempts - user_correct_answers
                accuracy = (user_correct_answers / user_total_attempts * 100) if user_total_attempts > 0 else 0

                # Update group totals
                total_group_quizzes += user_total_attempts
                total_correct_answers += user_correct_answers

                # Track active users
                last_activity = group_stats.get('last_activity_date')
                if last_activity:
                    if last_activity == today:
                        active_users_today.add(user_id)
                    if last_activity >= week_start:
                        active_users_week.add(user_id)
                    if last_activity >= month_start:
                        active_users_month.add(user_id)

                leaderboard.append({
                    'user_id': int(user_id),
                    'total_attempts': user_total_attempts,
                    'correct_answers': user_correct_answers,
                    'wrong_answers': user_wrong_answers,
                    'accuracy': round(accuracy, 1),
                    'score': group_stats.get('score', 0),
                    'last_active': group_stats.get('last_activity_date', 'Never')
                })

        # Sort by score and get top 10
        leaderboard.sort(key=lambda x: x['score'], reverse=True)

        # Calculate group performance metrics
        group_accuracy = (total_correct_answers / total_group_quizzes * 100) if total_group_quizzes > 0 else 0

        return {
            'total_quizzes': total_group_quizzes,
            'total_correct': total_correct_answers,
            'group_accuracy': round(group_accuracy, 1),
            'active_users': {
                'today': len(active_users_today),
                'week': len(active_users_week),
                'month': len(active_users_month),
                'total': len(leaderboard)
            },
            'leaderboard': leaderboard[:10]
        }

    def record_group_attempt(self, user_id: int, chat_id: int, is_correct: bool):
        """Record a quiz attempt for a user in a specific group with timestamp"""
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
                'longest_streak': 0
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
            if group_stats['last_activity_date'] == (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'):
                group_stats['current_streak'] += 1
            else:
                group_stats['current_streak'] = 1

            group_stats['longest_streak'] = max(group_stats['current_streak'], group_stats['longest_streak'])

        self.save_data()


    def add_question(self, question: str, options: List[str], correct_answer: int):
        self.questions.append({
            'question': question,
            'options': options,
            'correct_answer': correct_answer
        })
        self.save_data()

    def delete_question(self, index: int):
        if 0 <= index < len(self.questions):
            self.questions.pop(index)
            self.save_data()

    def get_random_question(self) -> Dict:
        if not self.questions:
            return None
        return random.choice(self.questions)

    def get_all_questions(self) -> List[Dict]:
        return self.questions

    def increment_score(self, user_id: int):
        user_id = str(user_id)
        if user_id not in self.scores:
            self.scores[user_id] = 0
        self.scores[user_id] += 1
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

    def get_leaderboard(self) -> List[Dict]:
        """Get top 10 users with their comprehensive statistics"""
        leaderboard = []
        for user_id, stats in self.stats.items():
            total_attempts = stats['total_quizzes']
            correct_answers = stats['correct_answers']
            wrong_answers = total_attempts - correct_answers
            accuracy = (correct_answers / total_attempts * 100) if total_attempts > 0 else 0

            leaderboard.append({
                'user_id': int(user_id),
                'total_attempts': total_attempts,
                'correct_answers': correct_answers,
                'wrong_answers': wrong_answers,
                'accuracy': round(accuracy, 1),
                'score': self.get_score(int(user_id))
            })

        # Sort by score and get top 10
        leaderboard.sort(key=lambda x: x['score'], reverse=True)
        return leaderboard[:10]