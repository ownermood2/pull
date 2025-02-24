document.addEventListener('DOMContentLoaded', function() {
    loadQuestions();

    document.getElementById('questionForm').addEventListener('submit', function(e) {
        e.preventDefault();
        
        const question = document.getElementById('question').value;
        const options = Array.from(document.getElementsByName('option[]'))
            .map(input => input.value);
        const correctAnswer = parseInt(document.querySelector('input[name="correct"]:checked').value);

        fetch('/api/questions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: question,
                options: options,
                correct_answer: correctAnswer
            })
        })
        .then(response => response.json())
        .then(() => {
            loadQuestions();
            document.getElementById('questionForm').reset();
        })
        .catch(error => console.error('Error:', error));
    });
});

function loadQuestions() {
    fetch('/api/questions')
        .then(response => response.json())
        .then(questions => {
            const questionList = document.getElementById('questionList');
            questionList.innerHTML = '';

            questions.forEach((question, index) => {
                const questionElement = document.createElement('div');
                questionElement.className = 'list-group-item';
                questionElement.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h5 class="mb-1">${question.question}</h5>
                            <ul class="list-unstyled">
                                ${question.options.map((option, i) => `
                                    <li>
                                        ${i === question.correct_answer ? '✅' : '⚪'} ${option}
                                    </li>
                                `).join('')}
                            </ul>
                        </div>
                        <button class="btn btn-danger btn-sm" onclick="deleteQuestion(${index})">
                            Delete
                        </button>
                    </div>
                `;
                questionList.appendChild(questionElement);
            });
        })
        .catch(error => console.error('Error:', error));
}

function deleteQuestion(index) {
    fetch(`/api/questions/${index}`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(() => loadQuestions())
    .catch(error => console.error('Error:', error));
}
