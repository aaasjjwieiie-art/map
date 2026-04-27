import os, time, threading
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Папка для фото
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///komek.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Сценарий 1: Ответы АВТОРА (когда ТЫ помогаешь кому-то)
ANSWERS = [
    "Салам! Рахмет, что отозвались. Помощь актуальна!",
    "Да, инструменты есть, только ваши руки нужны.",
    "Когда сможете подойти?",
    "Это не срочно, можно в любое время на выходных.",
    "Рахмет! Жду вас по адресу на карте."
]

# Сценарий 2: Ответы ПОМОЩНИКА (когда КТО-ТО пишет в ТВОЕ объявление)
HELPER_ANSWERS = [
    "Здравствуйте, готов вам помочь!",
    "В любое время.",
    "Хорошо, с собой что-то требуется взять?",
    "Отлично, до встречи!"
]

class HelpRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    category = db.Column(db.String(50), default='general')
    status = db.Column(db.String(20), default='open') 
    image_url = db.Column(db.String(200))
    author = db.Column(db.String(50), default='Аноним')
    rating = db.Column(db.Float, default=4.5)
    helped_count = db.Column(db.Integer, default=0)
    is_urgent = db.Column(db.Boolean, default=False)
    helper_name = db.Column(db.String(50), nullable=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('help_request.id'))
    text = db.Column(db.String(500))
    is_bot = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

def ai_reply_logic(task_id):
    time.sleep(2)
    with app.app_context():
        task = HelpRequest.query.get(task_id)
        if not task: return
        
        user_msg_count = Message.query.filter_by(task_id=task_id, is_bot=False).count()
        index = (user_msg_count - 1)
        
        # Если автор "Нурик Ж.", значит пишет внешний Помощник
        if task.author == "Нурик Ж.":
            if index < len(HELPER_ANSWERS):
                reply_text = HELPER_ANSWERS[index]
                bot_msg = Message(task_id=task_id, text=f"[Волонтер]: {reply_text}", is_bot=True)
                db.session.add(bot_msg)
                db.session.commit()
        else:
            # Если автор другой человек, бот отвечает как владелец задания
            if index < len(ANSWERS):
                reply_text = ANSWERS[index]
                bot_msg = Message(task_id=task_id, text=f"[Автор {task.author}]: {reply_text}", is_bot=True)
                db.session.add(bot_msg)
                db.session.commit()

def seed_data():
    if HelpRequest.query.count() == 0:
        fakes = [
            ("Помочь донести сумки", "Пожилой человек на 5 этаже, лифт не работает. Очень нужна помощь.", 43.238, 76.865, "general", "Мария И.", 4.9, 42, True),
            ("Субботник в парке", "Собираемся очистить рощу Баума от пластика. Мешки дадим!", 43.270, 76.940, "eco", "EcoAlmaty", 5.0, 156, False),
            ("Замена лампочек в подъезде", "Перегорели лампы на 3 этажах. Стремянка есть.", 43.220, 76.905, "repair", "Арман К.", 4.3, 8, False)
        ]
        for t, d, lat, lng, cat, auth, rat, h, urg in fakes:
            db.session.add(HelpRequest(title=t, description=d, lat=lat, lng=lng, category=cat, author=auth, rating=rat, helped_count=h, is_urgent=urg))
        db.session.commit()

@app.route('/api/tasks', methods=['GET', 'POST'])
def handle_tasks():
    if request.method == 'GET':
        tasks = HelpRequest.query.all()
        return jsonify([{
            "id": t.id, "title": t.title, "description": t.description, 
            "lat": t.lat, "lng": t.lng, "category": t.category, 
            "status": t.status, "image": t.image_url,
            "author": t.author, "rating": t.rating, "helped_count": t.helped_count,
            "is_urgent": t.is_urgent, "helper_name": t.helper_name
        } for t in tasks])
    
    if request.method == 'POST':
        new_task = HelpRequest(
            title=request.form.get('title'),
            description=request.form.get('description'),
            lat=float(request.form.get('lat')),
            lng=float(request.form.get('lng')),
            category=request.form.get('category'),
            is_urgent=(request.form.get('is_urgent') == 'true'),
            author="Нурик Ж.", rating=4.9, helped_count=12
        )
        file = request.files.get('image')
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            new_task.image_url = filename
        db.session.add(new_task)
        db.session.commit()
        return jsonify({"message": "Created"}), 201

@app.route('/api/tasks/<int:id>/help', methods=['POST'])
def help_task(id):
    task = HelpRequest.query.get_or_404(id)
    task.status = 'in_progress'
    task.helper_name = "Нурик Ж."
    db.session.commit()
    return jsonify({"message": "In progress"}), 200

@app.route('/api/tasks/<int:id>/complete', methods=['POST'])
def complete_task(id):
    task = HelpRequest.query.get_or_404(id)
    task.status = 'completed'
    db.session.commit()
    return jsonify({"message": "Done"}), 200

@app.route('/api/tasks/<int:id>', methods=['DELETE'])
def delete_task(id):
    task = HelpRequest.query.get_or_404(id)
    db.session.delete(task)
    db.session.commit()
    return jsonify({"message": "Deleted"}), 200

@app.route('/api/tasks/<int:task_id>/messages', methods=['GET', 'POST'])
def handle_messages(task_id):
    if request.method == 'GET':
        msgs = Message.query.filter_by(task_id=task_id).order_by(Message.timestamp.asc()).all()
        return jsonify([{"text": m.text, "time": m.timestamp.strftime("%H:%M"), "is_bot": m.is_bot} for m in msgs])
    if request.method == 'POST':
        data = request.json
        new_msg = Message(task_id=task_id, text=data['text'], is_bot=False)
        db.session.add(new_msg)
        db.session.commit()
        threading.Thread(target=ai_reply_logic, args=(task_id,)).start()
        return jsonify({"status": "ok"}), 201

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_data()
    app.run(debug=True, port=5000)