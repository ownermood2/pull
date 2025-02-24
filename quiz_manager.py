import json
import random
import os
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class QuizManager:
    def __init__(self):
        self.questions_file = "data/questions.json"
        self.scores_file = "data/scores.json"
        self.active_chats_file = "data/active_chats.json"
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

    def load_data(self):
        with open(self.questions_file, 'r') as f:
            self.questions = json.load(f)
        with open(self.scores_file, 'r') as f:
            self.scores = json.load(f)
        with open(self.active_chats_file, 'r') as f:
            self.active_chats = json.load(f)

    def save_data(self):
        with open(self.questions_file, 'w') as f:
            json.dump(self.questions, f)
        with open(self.scores_file, 'w') as f:
            json.dump(self.scores, f)
        with open(self.active_chats_file, 'w') as f:
            json.dump(self.active_chats, f)

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
        user_id = str(user_id)  # Convert to string for JSON compatibility
        if user_id not in self.scores:
            self.scores[user_id] = 0
        self.scores[user_id] += 1
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
