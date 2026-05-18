import os
import time
import threading
import math
import telebot

from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
CORS(app)

TOKEN = "7964218356:AAFIego96byHgIYPqJiKsGis4hnaERBETlQ"
bot = telebot.TeleBot(TOKEN)

CHAT_ID_FILE = "chat_id.txt"


def load_chat_id():
    if os.path.exists(CHAT_ID_FILE):
        try:
            with open(CHAT_ID_FILE, "r") as f:
                val = f.read().strip()
                if val:
                    return int(val)
        except Exception:
            pass
    return None


def save_chat_id(cid):
    try:
        with open(CHAT_ID_FILE, "w") as f:
            f.write(str(cid))
    except Exception as e:
        print(f"Ошибка сохранения chat_id: {e}")


USER_CONFIG = {
    "chat_id": load_chat_id()
}

PORT = int(os.environ.get("PORT", 5000))

UPLOAD_FOLDER = 'uploads'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///komek.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db = SQLAlchemy(app)

@app.route('/')
def index():
    return jsonify({
        "message": "Сервер Flask запущен и успешно работает!",
        "project": "KomekMap API",
        "status": "running",
        "version": "1.0.0"
    })

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


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(d_lat / 2) ** 2 +
        math.cos(math.radians(lat1)) *
        math.cos(math.radians(lat2)) *
        math.sin(d_lon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def send_tg_notification(text):
    if USER_CONFIG["chat_id"]:
        try:
            bot.send_message(
                USER_CONFIG["chat_id"],
                text,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Ошибка отправки в TG: {e}")


ANSWERS = [
    "Салам! Рахмет, что отозвались.",
    "Да, помощь ещё нужна.",
    "Инструменты есть.",
    "Когда сможете подойти?",
    "Рахмет!"
]

HELPER_ANSWERS = [
    "Здравствуйте! Готов помочь.",
    "Могу сегодня вечером.",
    "Что нужно взять с собой?",
    "Отлично!"
]


@bot.message_handler(commands=['start'])
def handle_start(message):
    USER_CONFIG["chat_id"] = message.chat.id
    save_chat_id(message.chat.id)

    bot.reply_to(
        message,
        "✅ KomekMap подключен"
    )


@bot.message_handler(commands=['profile'])
def handle_profile(message):

    with app.app_context():

        my_tasks = HelpRequest.query.filter_by(
            author="Нурик Ж."
        ).count()

        helping = HelpRequest.query.filter_by(
            helper_name="Нурик Ж.",
            status="in_progress"
        ).count()

        bot.send_message(
            message.chat.id,
            f"👤 Профиль: Нурик Ж.\n📢 Объявлений: {my_tasks}\n🏃 Помогаю: {helping}\n⭐ Рейтинг: 4.9"
        )


def run_bot_polling():
    bot.remove_webhook()
    bot.polling(none_stop=True)


def ai_reply_logic(task_id):

    time.sleep(2)

    with app.app_context():

        task = HelpRequest.query.get(task_id)

        if not task:
            return

        user_msg_count = Message.query.filter_by(
            task_id=task_id,
            is_bot=False
        ).count()

        index = user_msg_count - 1

        reply = ""

        if task.author == "Нурик Ж.":

            if index < len(HELPER_ANSWERS):
                reply = HELPER_ANSWERS[index]

        else:

            if index < len(ANSWERS):
                reply = ANSWERS[index]

        if reply:

            new_m = Message(
                task_id=task_id,
                text=f"[Бот]: {reply}",
                is_bot=True
            )

            db.session.add(new_m)
            db.session.commit()

            send_tg_notification(
                f"💬 Ответ собеседника по *«{task.title}»*:\n{reply}"
            )


def auto_first_message(task_id):

    time.sleep(3)

    with app.app_context():

        task = HelpRequest.query.get(task_id)

        if task and task.author == "Нурик Ж.":

            first_msg = "Здравствуйте! Готов помочь."

            new_m = Message(
                task_id=task_id,
                text=f"[Помощник]: {first_msg}",
                is_bot=True
            )

            db.session.add(new_m)
            db.session.commit()

            send_tg_notification(
                f"💬 Помощник написал по *«{task.title}»*:\n{first_msg}"
            )


@app.route('/api/tasks', methods=['GET', 'POST'])
def handle_tasks():

    if request.method == 'GET':

        u_lat = request.args.get('lat', type=float)
        u_lng = request.args.get('lng', type=float)
        radius = request.args.get('radius', type=float)

        tasks = HelpRequest.query.all()

        result = []

        for t in tasks:

            dist = None

            if u_lat and u_lng:
                dist = calculate_distance(
                    u_lat,
                    u_lng,
                    t.lat,
                    t.lng
                )

            if radius and dist and dist > radius:
                continue

            result.append({
                'id': t.id,
                'title': t.title,
                'description': t.description,
                'lat': t.lat,
                'lng': t.lng,
                'category': t.category,
                'status': t.status,
                'image': t.image_url,
                'author': t.author,
                'rating': t.rating,
                'is_urgent': t.is_urgent,
                'helper_name': t.helper_name,
                'distance': round(dist, 2) if dist else None
            })

        return jsonify(result)

    image_url = None

    if 'image' in request.files:

        file = request.files['image']

        if file and file.filename:

            filename = secure_filename(file.filename)

            filename = f"{int(time.time())}_{filename}"

            filepath = os.path.join(
                app.config['UPLOAD_FOLDER'],
                filename
            )

            file.save(filepath)

            image_url = filename

    new_task = HelpRequest(
        title=request.form.get('title'),
        description=request.form.get('description'),
        lat=float(request.form.get('lat')),
        lng=float(request.form.get('lng')),
        category=request.form.get('category'),
        is_urgent=request.form.get('is_urgent') == 'true',
        author='Нурик Ж.',
        rating=4.9,
        image_url=image_url
    )

    db.session.add(new_task)
    db.session.commit()

    threading.Thread(
        target=auto_first_message,
        args=(new_task.id,)
    ).start()

    send_tg_notification(
        f"📢 Новое объявление: {new_task.title}"
    )

    return jsonify({'message': 'created'}), 201


@app.route('/api/tasks/<int:id>/help', methods=['POST'])
def help_task(id):

    task = HelpRequest.query.get_or_404(id)

    if task.status == 'in_progress':
        return jsonify({'message': 'Task already taken'}), 400

    if task.status == 'completed':
        return jsonify({'message': 'Task completed'}), 400

    task.status = 'in_progress'
    task.helper_name = 'Нурик Ж.'

    db.session.commit()

    # Если задание чужое — уведомляем автора что кто-то откликнулся
    if task.author != 'Нурик Ж.':
        send_tg_notification(
            f"🙋 На ваше объявление *«{task.title}»* откликнулся помощник!\n"
            f"Он уже в пути. Ожидайте помощи."
        )
    else:
        send_tg_notification(
            f"🤝 Вы помогаете: {task.title}"
        )

    return jsonify({'message': 'OK'})


@app.route('/api/tasks/<int:id>/complete', methods=['POST'])
def complete_task(id):

    task = HelpRequest.query.get_or_404(id)

    task.status = 'completed'

    db.session.commit()

    return jsonify({'message': 'completed'})


@app.route('/api/tasks/<int:id>', methods=['DELETE'])
def delete_task(id):

    task = HelpRequest.query.get_or_404(id)

    db.session.delete(task)

    db.session.commit()

    return jsonify({'message': 'deleted'})


@app.route('/api/tasks/<int:task_id>/messages', methods=['GET', 'POST'])
def handle_messages(task_id):

    if request.method == 'GET':

        msgs = Message.query.filter_by(
            task_id=task_id
        ).order_by(
            Message.timestamp.asc()
        ).all()

        return jsonify([
            {
                'text': m.text,
                'time': m.timestamp.strftime('%H:%M'),
                'is_bot': m.is_bot
            }
            for m in msgs
        ])

    data = request.json

    new_msg = Message(
        task_id=task_id,
        text=data['text'],
        is_bot=False
    )

    db.session.add(new_msg)
    db.session.commit()

    # Уведомление в Telegram при новом сообщении
    task = HelpRequest.query.get(task_id)
    if task:
        send_tg_notification(
            f"💬 Новое сообщение по объявлению *«{task.title}»*:\n{data['text']}"
        )

    threading.Thread(
        target=ai_reply_logic,
        args=(task_id,)
    ).start()

    return jsonify({'status': 'ok'})


@app.route('/api/sos_alert', methods=['POST'])
def sos_alert():

    data = request.json

    send_tg_notification(
        f"🚨 SOS\nШирота: {data['lat']}\nДолгота: {data['lng']}"
    )

    return jsonify({'status': 'ok'})


@app.route('/uploads/<filename>')
def uploaded_file(filename):

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename
    )


def seed_tasks():

    if HelpRequest.query.count() > 0:
        return

    demo_tasks = [

        HelpRequest(
            title='Помочь починить калитку',
            description='Пенсионеру нужен шуруповерт.',
            lat=47.7833,
            lng=67.7099,
            category='repair',
            author='Серик А.',
            rating=4.8,
            is_urgent=True
        ),

        HelpRequest(
            title='Уборка двора',
            description='Нужны волонтёры для субботника.',
            lat=47.7901,
            lng=67.7150,
            category='eco',
            author='Айман К.',
            rating=4.7
        ),

        HelpRequest(
            title='Доставить продукты',
            description='Бабушка не может выйти из дома.',
            lat=47.8012,
            lng=67.7265,
            category='delivery',
            author='Галина П.',
            rating=4.9
        ),

        HelpRequest(
            title='Помочь перенести уголь',
            description='Нужно 2 человека.',
            lat=47.7950,
            lng=67.7001,
            category='general',
            author='Бауыржан С.',
            rating=4.6
        )

    ]

    db.session.add_all(demo_tasks)

    db.session.commit()


if __name__ == '__main__':

    threading.Thread(
        target=run_bot_polling,
        daemon=True
    ).start()

    with app.app_context():

        db.create_all()

        seed_tasks()

    app.run(
      host='0.0.0.0',
        port=PORT,
        debug=False
    )