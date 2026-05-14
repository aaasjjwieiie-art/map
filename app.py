import os, time, threading, math, requests
import telebot
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
CORS(app)

# --- НАСТРОЙКИ TELEGRAM ---
TOKEN = "7964218356:AAFIego96byHgIYPqJiKsGis4hnaERBETlQ"
bot = telebot.TeleBot(TOKEN)
USER_CONFIG = {"chat_id": None} 

def send_tg_notification(text):
    if USER_CONFIG["chat_id"]:
        try:
            bot.send_message(USER_CONFIG["chat_id"], text, parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка отправки в TG: {e}")

# --- ГЕО-ЛОГИКА ---
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- КОНФИГУРАЦИЯ БД ---
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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

# --- ШАБЛОНЫ ОТВЕТОВ ---
ANSWERS = ["Салам! Рахмет, что отозвались. Помощь актуальна!", "Да, инструменты есть, только ваши руки нужны.", "Когда сможете подойти?", "Это не срочно, можно в любое время.", "Рахмет! Жду вас."]
HELPER_ANSWERS = ["Здравствуйте, готов вам помочь!", "В любое время.", "Хорошо, с собой что-то требуется взять?", "Отлично, до встречи!"]

# --- TG BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    USER_CONFIG["chat_id"] = message.chat.id
    bot.reply_to(message, "✅ Система KomekMap активна! Вы будете получать уведомления о чатах и SOS.")

@bot.message_handler(commands=['profile'])
def handle_profile(message):
    with app.app_context():
        my_tasks = HelpRequest.query.filter_by(author="Нурик Ж.").count()
        helping = HelpRequest.query.filter_by(helper_name="Нурик Ж.", status="in_progress").count()
        bot.send_message(message.chat.id, f"👤 *Профиль: Нурик Ж.*\n📢 Объявлений: {my_tasks}\n🏃 Помогаю: {helping}\n⭐ Рейтинг: 4.9", parse_mode="Markdown")

def run_bot_polling():
    bot.remove_webhook()
    bot.polling(none_stop=True)

# --- ЛОГИКА АВТО-ОТВЕТОВ ---
def ai_reply_logic(task_id):
    time.sleep(2)
    with app.app_context():
        task = HelpRequest.query.get(task_id)
        if not task: return
        user_msg_count = Message.query.filter_by(task_id=task_id, is_bot=False).count()
        index = (user_msg_count - 1)
        reply = ""
        if task.author == "Нурик Ж.":
            if index < len(HELPER_ANSWERS): reply = HELPER_ANSWERS[index]
        else:
            if index < len(ANSWERS): reply = ANSWERS[index]
        if reply:
            new_m = Message(task_id=task_id, text=f"[{'Помощник' if task.author == 'Нурик Ж.' else 'Автор'}]: {reply}", is_bot=True)
            db.session.add(new_m); db.session.commit()
            send_tg_notification(f"📩 Ответ в чате [{task.title}]:\n_{reply}_")

def auto_first_message(task_id):
    """Автоматически пишет пользователю, когда он создал объявление"""
    time.sleep(3)
    with app.app_context():
        task = HelpRequest.query.get(task_id)
        if task and task.author == "Нурик Ж.":
            first_msg = "Здравствуйте! Увидел ваше объявление, готов помочь. Когда вам удобно?"
            new_m = Message(task_id=task_id, text=f"[Помощник]: {first_msg}", is_bot=True)
            db.session.add(new_m); db.session.commit()
            send_tg_notification(f"🤝 Потенциальный помощник написал вам по задаче *{task.title}*:\n_{first_msg}_")
@app.route('/')
def index():
    return jsonify({
        "status": "online",
        "message": "Система KomekMap активна. Используйте /api/tasks для получения данных.",
        "author": "Нурик Ж."
    })
# --- API ---
@app.route('/api/tasks', methods=['GET', 'POST'])
def handle_tasks():
    if request.method == 'GET':
        u_lat, u_lng, radius = request.args.get('lat', type=float), request.args.get('lng', type=float), request.args.get('radius', type=float)
        tasks = HelpRequest.query.all()
        result = []
        for t in tasks:
            dist = calculate_distance(u_lat, u_lng, t.lat, t.lng) if u_lat and u_lng else None
            if radius and dist and dist > radius: continue
            result.append({"id": t.id, "title": t.title, "description": t.description, "lat": t.lat, "lng": t.lng, "category": t.category, "status": t.status, "image": t.image_url, "author": t.author, "rating": t.rating, "is_urgent": t.is_urgent, "helper_name": t.helper_name, "distance": round(dist, 2) if dist else None})
        return jsonify(result)
    
    if request.method == 'POST':
        new_task = HelpRequest(title=request.form.get('title'), description=request.form.get('description'), lat=float(request.form.get('lat')), lng=float(request.form.get('lng')), category=request.form.get('category'), is_urgent=(request.form.get('is_urgent') == 'true'), author="Нурик Ж.", rating=4.9)
        db.session.add(new_task); db.session.commit()
        send_tg_notification(f"📢 Объявление *{new_task.title}* опубликовано.")
        # ЗАПУСК АВТО-ОТКЛИКА
        threading.Thread(target=auto_first_message, args=(new_task.id,)).start()
        return jsonify({"message": "Created"}), 201

@app.route('/api/tasks/<int:id>/help', methods=['POST'])
def help_task(id):
    task = HelpRequest.query.get_or_404(id)
    task.status = 'in_progress'; task.helper_name = "Нурик Ж."; db.session.commit()
    send_tg_notification(f"🤝 Вы помогаете по задаче: *{task.title}*")
    return jsonify({"message": "OK"}), 200

@app.route('/api/tasks/<int:id>/complete', methods=['POST'])
def complete_task(id):
    task = HelpRequest.query.get_or_404(id); task.status = 'completed'; db.session.commit()
    send_tg_notification(f"🎉 Завершено: *{task.title}*")
    return jsonify({"message": "OK"}), 200

@app.route('/api/tasks/<int:id>', methods=['DELETE'])
def delete_task(id):
    task = HelpRequest.query.get_or_404(id); db.session.delete(task); db.session.commit()
    return jsonify({"message": "Deleted"}), 200

@app.route('/api/tasks/<int:task_id>/messages', methods=['GET', 'POST'])
def handle_messages(task_id):
    if request.method == 'GET':
        msgs = Message.query.filter_by(task_id=task_id).order_by(Message.timestamp.asc()).all()
        return jsonify([{"text": m.text, "time": m.timestamp.strftime("%H:%M"), "is_bot": m.is_bot} for m in msgs])
    if request.method == 'POST':
        data = request.json
        new_msg = Message(task_id=task_id, text=data['text'], is_bot=False)
        db.session.add(new_msg); db.session.commit()
        task = HelpRequest.query.get(task_id)
        send_tg_notification(f"💬 Сообщение [{task.title}]:\n_{data['text']}_")
        threading.Thread(target=ai_reply_logic, args=(task_id,)).start()
        return jsonify({"status": "ok"}), 201

@app.route('/api/sos_alert', methods=['POST'])
def sos_alert():
    data = request.json
    send_tg_notification(f"🚨 *SOS!* Нурику Ж. нужна помощь!\nКоординаты: {data['lat']}, {data['lng']}")
    return jsonify({"status": "ok"})

def seed_tasks():
    if HelpRequest.query.count() == 0:
        db.session.add_all([
            HelpRequest(title="Починить забор", description="Нужна помощь с инструментами.", lat=43.245, lng=76.910, category="repair", author="Аскар Е.", is_urgent=True),
            HelpRequest(title="Вынос мусора", description="Строительный мусор, 4 этаж.", lat=43.230, lng=76.890, category="general", author="Бабушка Вера")
        ])
        db.session.commit()

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
        threading.Thread(target=run_bot_polling, daemon=True).start()
        with app.app_context():
            db.create_all()
            seed_tasks()
        # Render сам назначит порт через переменную окружения
        port = int(os.environ.get("PORT", 5000))
        app.run(host='0.0.0.0', port=port)