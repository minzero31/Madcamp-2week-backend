from flask import Flask, request, jsonify
import mysql.connector
from mysql.connector import Error
import base64
import requests
import google.generativeai as genai
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Google Vision API Key
VISION_API_KEY = 'Enter API Key'  # 여기에 실제 API Key를 입력하세요

# Google Gemini API Key
GEMINI_API_KEY = 'Enter API Key'  # 여기에 실제 Google Gemini API Key를 입력하세요

# Google Gemini API 설정
genai.configure(api_key=GEMINI_API_KEY)

# 데이터베이스 연결 설정 함수
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host="localhost",  # kcloud and mysql are in same server
            user="new_user",
            password="StrongPassw0rd!",
            database="madcamp_2"
        )
        if connection.is_connected():
            print("Successfully connected to the database")
        return connection
    except Error as err:
        print(f"Error: {err}")
        return None

# 애플리케이션 시작 시 데이터베이스 연결 테스트
db = get_db_connection()
if db is None:
    print("Failed to connect to the database")

@app.route('/login', methods=['POST'])
def login():
    if db is None or not db.is_connected():
        return jsonify({"message": "Database connection is not available"}), 500

    data = request.json
    username = data['username']
    password = data['password']

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
    user = cursor.fetchone()
    cursor.close()

    if user:
        print(f"Login successful for user: {username}")
        return jsonify({"message": "Login successful", "username": username, "email": user['email']}), 200
    else:
        print(f"Login failed for user: {username}")
        return jsonify({"message": "Invalid credentials"}), 401

@app.route('/signup', methods=['POST'])
def signup():
    if db is None or not db.is_connected():
        return jsonify({"message": "Database connection is not available"}), 500

    data = request.json
    username = data['username']
    email = data['email']
    password = data['password']

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()
    if user:
        cursor.close()
        print(f"Signup failed: Username {username} already exists")
        return jsonify({"message": "Username already exists"}), 400

    cursor.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", (username, email, password))
    db.commit()
    cursor.close()
    print(f"Signup successful for user: {username}")
    return jsonify({"message": "Signup successful. Please log in."}), 201

@app.route('/upload_image', methods=['POST'])
def upload_image():
    base64_image = request.data.decode('utf-8')

    # Google Vision API 요청 URL
    vision_url = f'https://vision.googleapis.com/v1/images:annotate?key={VISION_API_KEY}'

    # API 요청 데이터 구성
    headers = {'Content-Type': 'application/json'}
    data = {
        "requests": [
            {
                "image": {
                    "content": base64_image
                },
                "features": [
                    {
                        "type": "TEXT_DETECTION"
                    }
                ]
            }
        ]
    }

    # Google Vision API 호출
    vision_response = requests.post(vision_url, headers=headers, json=data)
    vision_data = vision_response.json()

    # 응답 데이터 출력 (디버깅 용도)
    print("Google Vision API 응답 데이터:", vision_data)

    # OCR 결과 추출
    try:
        if 'responses' in vision_data and 'textAnnotations' in vision_data['responses'][0]:
            ocr_text = vision_data['responses'][0]['textAnnotations'][0]['description']
        else:
            ocr_text = "OCR 결과가 없습니다."
    except KeyError as e:
        print(f"KeyError 발생: {e}")
        ocr_text = "응답 데이터 형식 오류."

    if ocr_text not in ["OCR 결과가 없습니다.", "응답 데이터 형식 오류."]:
        # Google Gemini API를 사용하여 문제 생성
        try:
            model = genai.GenerativeModel('gemini-pro')
            prompt = (f'Create seven exam questions based on the following text: "{ocr_text}". '
                      f'All questions and answer choices must be in Korean. '
                      f'Format each question as "#####. [질문]?". '
                      f'Generate multiple-choice questions with five answer choices'
                      f'Format each choices as "$$$$$. [선택지 내용]".'
                      f'At the end, provide the 7 correct answer numbers for each question as a string of 7 digits(each 1 to 5) concatenated together.')
            gemini_response = model.generate_content(prompt)

            # 질문 추출
            questions = gemini_response.text.split('\n') if gemini_response and gemini_response.text else ["문제를 생성할 수 없습니다."]

            print(questions)

            # 문자열에서 숫자만 추출하는 함수
            def extract_numbers(input_string):
                numbers = [char for char in input_string if char.isdigit()]
                result = ''.join(numbers)
                return result
            
            # 문제 파싱
            questions_list=[]
            options_list=[]
            answers_list=[]
            options=[]

            for sentence in questions:
                if "#" in sentence and sentence in questions[:-3]:
                    questions_list.append(sentence.replace('*','').replace('#','').replace('.',''))
                elif "$" in sentence:
                        options.append(sentence.replace('$', '').replace('.',''))
                elif sentence!='' and ("답변" in sentence or "정답" in sentence or "Answer" in sentence or "answer" in sentence):
                    ex_sentence = extract_numbers(sentence)
                    if ex_sentence!='':
                        answers_list.append(ex_sentence)
            answers_list = [int(char) for char in answers_list[0]]
            
            for i in range(7):
                op=[]
                for j in range(5):
                    op.append(options[i*5+j])
                options_list.append(op)


            print(questions_list)
            print(options_list)
            print(answers_list)

            
        except Exception as e:
            error_message = f"Failed to generate questions: {e}"
            print(error_message)
            return jsonify({"error": "Failed to generate questions"}), 500

        return jsonify({"ocrText": ocr_text, "questions": questions_list, "options": options_list, "answers": answers_list})
    else:
        return jsonify({"ocrText": ocr_text, "questions": []})

@app.route('/save_exam', methods=['POST'])
def save_exam():
    data = request.json
    username = data.get('username')
    exam_name = data.get('exam_name')
    problems = data.get('problems')

    if not username or not exam_name or not problems:
        return jsonify({"message": "Invalid data"}), 400

    try:
        cursor = db.cursor()

        # Log received data
        print(f"Received data: username={username}, exam_name={exam_name}, problems={problems}")
        
        # Insert into Exam table
        cursor.execute("INSERT INTO exam (username, exam_name) VALUES (%s, %s)", (username, exam_name))
        db.commit()
        exam_id = cursor.lastrowid
        
        # Insert into Problems table
        for problem in problems:
            question = problem['question']
            option1 = problem['option1']
            option2 = problem['option2']
            option3 = problem['option3']
            option4 = problem['option4']
            option5 = problem['option5']
            answer = problem['answer']
            cursor.execute("""
                INSERT INTO problems (exam_id, question, option1, option2, option3, option4, option5, answer) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (exam_id, question, option1, option2, option3, option4, option5, answer))
        
        db.commit()
        cursor.close()

        return jsonify({"message": "Exam saved successfully"}), 200
    except Error as err:
        print(f"Error: {err}")
        return jsonify({"message": f"Failed to save exam: {err}"}), 500

@app.route('/exams', methods=['POST'])
def get_exams():
    data = request.json
    username = data.get('username')

    if db is None or not db.is_connected():
        return jsonify({"message": "Database connection is not available"}), 500

    cursor = db.cursor(dictionary=True)
    # 다른 사용자의 exams를 가져오기 위해 username != %s로 조건을 수정합니다.
    cursor.execute("SELECT exam_id, exam_name FROM exam WHERE username != %s", (username,))
    exams = cursor.fetchall()

    exam_data = []
    for exam in exams:
        cursor.execute("SELECT question, option1, option2, option3, option4, option5, answer FROM problems WHERE exam_id = %s", (exam['exam_id'],))
        problems = cursor.fetchall()
        exam['questions'] = [problem['question'] for problem in problems]
        exam['options'] = [[problem['option1'], problem['option2'], problem['option3'], problem['option4'], problem['option5']] for problem in problems]
        exam['answers'] = [problem['answer'] for problem in problems]
        exam_data.append(exam)

    cursor.close()

    return jsonify(exam_data), 200

@app.route('/get_my_exams', methods=['POST'])
def get_my_exams():
    data = request.json
    username = data.get('username')

    if db is None or not db.is_connected():
        return jsonify({"message": "Database connection is not available"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT exam_id, exam_name, username FROM exam WHERE username = %s", (username,))
    exams = cursor.fetchall()

    exam_data = []
    for exam in exams:
        cursor.execute("SELECT question, option1, option2, option3, option4, option5, answer FROM problems WHERE exam_id = %s", (exam['exam_id'],))
        problems = cursor.fetchall()
        exam['questions'] = [problem['question'] for problem in problems]
        exam['options'] = [[problem['option1'], problem['option2'], problem['option3'], problem['option4'], problem['option5']] for problem in problems]
        exam['answers'] = [problem['answer'] for problem in problems]
        exam['username'] = exam['username']  # 추가된 부분
        exam_data.append(exam)

    cursor.close()

    return jsonify(exam_data), 200


@app.route('/health', methods=['GET'])
def health():
    if db is not None and db.is_connected():
        return jsonify({"status": "Database connection is healthy"}), 200
    else:
        return jsonify({"status": "Database connection is not healthy"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
