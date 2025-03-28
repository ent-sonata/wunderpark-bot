import telebot
import base64
import urllib
import schedule
import re
import pymysql
import requests
import threading
import os
import time
import hashlib

import xml.etree.ElementTree as ET

from icalendar import Calendar
from telebot import types
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

token_bot = os.getenv("BOT_TOKEN")

api_yandex = os.getenv("API_KEY")
email_yandex = os.getenv("EMAIL")
password_yandex = os.getenv("PASSWORD")

db_host = os.getenv("DB_HOST")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_database = os.getenv("DB_DATABASE")


TOKEN = token_bot
bot = telebot.TeleBot(TOKEN)

user_data = {}
user_selections = {}


# DB
db_config = {
    'host': db_host,
    'user': db_user,
    'password': db_password,
    'database': db_database
}



# FORMAT DATE
months = {
    1: "января", 2: "февраля", 3: "марта",
    4: "апреля", 5: "мая", 6: "июня",
    7: "июля", 8: "августа", 9: "сентября",
    10: "октября", 11: "ноября", 12: "декабря"
}

def format_date(date_str):
    """Конвертирования даты в нужный формат"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        day = date_obj.day
        month = months[date_obj.month]

        return f"{day} {month}"

    except Exception as e:
        print(f"Ошибка форматирования даты: {e}")
        return date_str

def format_datetime_calendar(dt):
    """Конвертирования даты в нужный формат для календаря без года"""
    try:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        day = dt.day
        month = months[dt.month]
        time = dt.strftime("%H:%M")

        return f"{day} {month}", time

    except Exception as e:
        print(f"Ошибка форматирования даты: {e}")
        return None, None

def format_full_datetime_calendar(dt):
    """Конвертирования даты в нужный формат для календаря с годом"""
    try:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        day = dt.day
        month = months[dt.month]
        year = dt.year
        time = dt.strftime("%H:%M")

        return f"{day} {month} {year} года", time

    except Exception as e:
        print(f"Ошибка форматирования даты: {e}")
        return None, None



# CHECK COMMAND START
def is_start_command(message):
    """Проверяем была ли отправлена команде /start"""
    return message.text and message.text.startswith('/start')



# UPDATE USERS
import pymysql

def update_user_data(user):
    """Добавление/обновление пользователей в БД"""
    try:
        connection = pymysql.connect(**db_config)

        with connection.cursor() as cursor:
            # Проверяем, есть ли пользователь с таким chat_id и event
            sql_check_query = "SELECT id FROM registrations WHERE chat_id = %s AND event = %s"
            cursor.execute(sql_check_query, (user['chat_id'], user['event']))  # Исправлено: теперь передаётся chat_id
            existing_user = cursor.fetchone()

            if existing_user:
                # Обновляем данные, если пользователь уже есть
                sql_update_query = """
                UPDATE registrations 
                SET name = %s, phone = %s, email = %s, participation = %s, track = %s, sections = %s, 
                    status = %s, location = %s, date_event = %s, time_event = %s, transport = %s  
                WHERE chat_id = %s AND event = %s
                """
                data_tuple = (
                    user['name'],
                    user['phone'],
                    user['email'],
                    user['participation'],
                    user['track'],
                    user['sections'],
                    user['status'],
                    user['location'],
                    user['date_event'],
                    user['time_event'],
                    user['transport'],
                    user['chat_id'],  # WHERE chat_id = %s
                    user['event']      # AND event = %s
                )
                cursor.execute(sql_update_query, data_tuple)
                print(f"✅ Данные пользователя {user['name']} (chat_id={user['chat_id']}) обновлены для события '{user['event']}'.")
            else:
                # Добавляем нового пользователя, если его нет
                sql_insert_query = """
                INSERT INTO registrations (name, phone, email, participation, track, sections, status, created_at, chat_id, event, location, date_event, time_event, transport)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                data_tuple = (
                    user['name'],
                    user['phone'],
                    user['email'],
                    user['participation'],
                    user['track'],
                    user['sections'],
                    user['status'],
                    user['created_at'],
                    user['chat_id'],
                    user['event'],
                    user['location'],
                    user['date_event'],
                    user['time_event'],
                    user['transport']
                )
                cursor.execute(sql_insert_query, data_tuple)
                print(f"✅ Новый пользователь {user['name']} (chat_id={user['chat_id']}) добавлен для события '{user['event']}'.")

            connection.commit()
    except Exception as e:
        print(f"❌ Ошибка при обновлении/добавлении данных: {e}")
    finally:
        connection.close()



# GET URL LOCATION
API_KEY = api_yandex

def get_yandex_maps_link(address):
    """Конвертирования локации в ссылку"""
    encoded_address = urllib.parse.quote(address)
    maps_link = f"https://yandex.ru/maps/?text={encoded_address}"
    return maps_link



# GET YANDEX CALENDAR
def get_all_events():
    """Получение событий из календаря"""
    email = email_yandex
    password = password_yandex

    auth_string = f"{email}:{password}"
    base64_auth = base64.b64encode(auth_string.encode()).decode()

    headers = {
        "Authorization": f"Basic {base64_auth}",
        "Depth": "1",
        "Content-Type": "application/xml"
    }

    caldav_url = f"https://caldav.yandex.ru/calendars/{email}/events-default/"

    data = """<?xml version="1.0" encoding="UTF-8" ?>
    <C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
        <D:prop>
            <D:getetag />
            <C:calendar-data />
        </D:prop>
        <C:filter>
            <C:comp-filter name="VCALENDAR">
                <C:comp-filter name="VEVENT"/>
            </C:comp-filter>
        </C:filter>
    </C:calendar-query>
    """

    response = requests.request("REPORT", caldav_url, headers=headers, data=data)

    if response.status_code == 207:
        print("Успешный запрос!")
    else:
        print(f"Ошибка {response.status_code}: {response.text}")

    root = ET.fromstring(response.text)

    global events
    events = []

    for response in root.findall(".//{DAV:}response"):
        for propstat in response.findall(".//{DAV:}propstat"):
            for prop in propstat.findall(".//{DAV:}prop"):
                for calendar_data in prop.findall(".//{urn:ietf:params:xml:ns:caldav}calendar-data"):
                    ics_content = calendar_data.text.strip()
                    cal = Calendar.from_ical(ics_content)

                    for component in cal.walk():
                        if component.name == "VEVENT":
                            summary = component.get("summary", "Без названия")
                            dtstart = component.get("dtstart").dt
                            dtend = component.get("dtend").dt
                            description = component.get("description", "Нет описания")
                            location = component.get("location", "Локация не указана")

                            events.append({
                                "name": summary,
                                "datetime": dtstart,
                                "dateend": dtend,
                                "location": location,
                                "description": description,
                            })



# GET NEAREST EVENT
def get_nearest_event():
    """Поиск ближайшего события"""
    global events

    now = datetime.now()
    future_events = [event for event in events if event["datetime"].replace(tzinfo=None) > now]

    if not future_events:
        return None

    nearest_event = min(future_events, key=lambda e: e["datetime"].replace(tzinfo=None))
    return nearest_event


# GET TODAY EVENT
def get_today_events():
    """Поиск всех мероприятий на текущий день"""
    global events

    now = datetime.now()
    today_events = [event for event in events if event["datetime"].date() == now.date()]

    return today_events if today_events else None



# GET CHAT ID AND USER DATA
def get_check_values():
    """Получаем айди чата в боте и статус регистрации пользователя"""
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute("SELECT chat_id, status FROM registrations")
    chat_data = [(row[0], row[1]) for row in cursor.fetchall()]

    conn.close()
    return chat_data

def get_track(chat_id):
    """Получаем трек по chat_id"""
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute("SELECT track FROM registrations WHERE chat_id = %s", (chat_id,))
    result = cursor.fetchone()

    conn.close()
    return result[0] if result else None

def get_participation(chat_id):
    """Получаем формат участия по chat_id"""
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute("SELECT participation FROM registrations WHERE chat_id = %s", (chat_id,))
    result = cursor.fetchone()

    conn.close()
    return result[0] if result else None



# SEND SURVEY
def schedule_survey(chat_id, event_end_time):
    """Ждём час после завершения мероприятия"""
    wait_time = (event_end_time + timedelta(hours=1)) - datetime.now()
    wait_seconds = max(wait_time.total_seconds(), 0)
    time.sleep(wait_seconds)
    send_survey(bot, chat_id)

def send_event_surveys():
    """Проверяем прошедшие мероприятия и отправляем опрос через час после завершения"""
    get_all_events()
    today_events = get_today_events()

    if today_events:
        now = datetime.now(timezone.utc)

        for event in today_events:
            event_end_time = event["dateend"]

            if event_end_time.tzinfo is None:
                event_end_time = event_end_time.replace(tzinfo=timezone.utc)
            else:
                event_end_time = event_end_time.astimezone(timezone.utc)

            time_since_event = now - event_end_time

            if timedelta(hours=1) - timedelta(minutes=1) <= time_since_event <= timedelta(hours=1) + timedelta(minutes=1):
                print(f"✅ Отправка опроса для {event['name']}")

                chat_data = get_check_values()
                confirmed_chat_ids = [chat_id for chat_id, status in chat_data if status == "Confirmed"]

                for chat_id in confirmed_chat_ids:
                    threading.Thread(target=send_survey, args=(chat_id, event['name']), daemon=True).start()
            else:
                print(f"⏳ Время опроса для {event['name']} еще не наступило: {event_end_time} (разница: {time_since_event}).")

    else:
        print("❌ Сегодня мероприятий нет.")

def send_survey(chat_id, event_name):
    """Отправляем анонимный опрос"""
    question = f"Как вам мероприятие '{event_name}'?"
    options = ["Отлично", "Хорошо", "Средне", "Не понравилось"]

    try:
        poll_message = bot.send_poll(chat_id, question, options, is_anonymous=True)
        poll_id = poll_message.poll.id
    except Exception as e:
        print(f"Ошибка при отправке опроса пользователю {chat_id}: {e}")



# SEND NOTIFICATIONS
def send_reminder_messages(event, label):
    """Отправляем напоминание о предстоящем мероприятии"""
    chat_data = get_check_values()

    confirmed_chat_ids = [chat_id for chat_id, status in chat_data if status == "Confirmed"]

    if event:
        date, time = format_datetime_calendar(event["datetime"])

        for chat_id in confirmed_chat_ids:
            message, markup = "", None

            if label == "week":
                message = (f"Привет!\n"
                           f"Напоминаю, что Вы зарегистрировались на Научно-практическую конференцию *{event['name']}*, "
                           f"которая состоится в *{event['location']} {date}*. \n\n"
                           f"🕒 *Начало мероприятия:* {time}\n\n"
                           f"Этот день определенно будет насыщенным! Поговорим о главных вызовах современной модели образования с ТОП-экспертами, "
                           f"опробуем новые методики, познакомимся с искусственным интеллектом, посетим книжную ярмарку и по-новому взглянем на просмотр кино!\n\n"
                           f"Среди спикеров — директора инновационных школ России, профессиональные конфликтологи и психологи, "
                           f"эксперты в области предпринимательства для школьников, заслуженные педагоги и многие другие!\n\n"
                           f"Подробнее обо всем, включая тайминг и темы докладов, смотрите в нашей программе.\n\n"
                           f"Отличного дня и Wunder-настроения!")

                markup = types.InlineKeyboardMarkup()
                btn_map = types.InlineKeyboardButton("Ссылка на программу", url="https://wunderpark.ru")
                markup.add(btn_map)

            elif label == "one_day":
                message = (f"Привет! Уже завтра большая Wunder-конференция! \n\n"
                           f"Ждем Ваc в *{event['location']}:* c *9:30*\n"
                           f"Приходите заранее — будет время взять именной бейджик участника у наших администраторов, "
                           f"пообщаться с коллегами и познакомиться с единомышленниками!\n\n"
                           f"Начнем в *{time}* в атриуме школы.\n\n"
                           f"До встречи!\n\n"
                           f"📍 *Адрес:* Wunderpark International School, д Борзые, д 1\n"
                           f"🕒 *Начало регистрации:* 9:30")

                maps_link = get_yandex_maps_link(event['location'])
                markup = types.InlineKeyboardMarkup()
                btn_map = types.InlineKeyboardButton("Карта", url=maps_link)
                markup.add(btn_map)

            elif label == "today":
                event = get_nearest_event()

                if event:
                    sections = event['description'].strip().split('\n\n')

                    teacher_online_sections = []
                    parent_online_sections = []

                    category = None

                    for section in sections:
                        if "(Онлайн учительский)" in section:
                            category = "Онлайн учительский"
                        elif "(Онлайн родительский)" in section:
                            category = "Онлайн родительский"

                        if category == "Онлайн учительский":
                            clean_section = section.replace("(Онлайн учительский)", "").strip()
                            teacher_online_sections.append(clean_section)
                        elif category == "Онлайн родительский":
                            clean_section = section.replace("(Онлайн родительски)", "").strip()
                            parent_online_sections.append(clean_section)

                    track = get_track(chat_id)
                    formate = get_participation(chat_id)

                    sections_to_send = []

                    if formate == "Онлайн":
                        if track == "Учительский":
                            sections_to_send = teacher_online_sections
                        elif track == "Родительский":
                            sections_to_send = parent_online_sections
                        else:
                            sections_to_send = []

                    if sections_to_send:
                        markup = types.InlineKeyboardMarkup(row_width=1)

                        for section in sections_to_send:
                            section_block = section.split('\n\n')

                            for section_stroke in section_block:
                                section_lines = section_stroke.split('\n')

                                if not section_lines:
                                    continue

                                first_line = section_lines[0] # Название
                                second_line = section_lines[1] if len(section_lines) > 1 else "" # Текст
                                second_line = re.split(r"\s+(?=http)", second_line)[0]
                                link_line = next((line for line in reversed(section_lines) if line.startswith("http")), "") # Ссылка

                                if not second_line.strip():
                                    continue

                                btn = types.InlineKeyboardButton(
                                    generate_button_text(first_line, second_line),
                                    url=link_line
                                )

                                markup.add(btn)

                                if formate == "Онлайн":
                                    message = (f"Привет! Сегодня начинается большая Wunder-конференция! 🎉\n\n"
                                               f"🕒 *Начало мероприятия:* {time}\n\n"
                                               f"Приятного просмотра!\n"
                                               f"Вот секции, на которые Вы записались:")

            if message:
                try:
                    bot.send_message(chat_id, message, reply_markup=markup, parse_mode="Markdown")
                except Exception as e:
                    print(f"Ошибка при отправке сообщения пользователю {chat_id}: {e}")

def send_event_reminders():
    """Проверяем, есть ли события, которые начинаются через 7 дней, 1 день, за 4 часа или 10 минут"""
    get_all_events()
    event = get_nearest_event()

    if event:
        now = datetime.now(timezone.utc)
        reminder_intervals = {
            "week": timedelta(days=7),
            "one_day": timedelta(days=1),
            "today": timedelta(hours=4),
            "test": timedelta(minutes=10)
        }

        event_time = event["datetime"]
        time_until_event = event_time - now

        for label, interval in reminder_intervals.items():
            if interval - timedelta(minutes=1) <= time_until_event <= interval + timedelta(minutes=1):
                print(f"Отправка напоминания для {event['name']} ({label})")
                send_reminder_messages(event, label)

    else:
        print("Нет запланированных мероприятий.")

def schedule_checker():
    """Запускаем планировщик для напоминаний в отдельном потоке"""
    while True:
        schedule.run_pending()
        time.sleep(1)


# STEP 1
@bot.message_handler(commands=['start'])
def start(message):
    """Действие бота на команду /start"""
    chat_id = message.chat.id

    user_data[chat_id] = {}
    user_selections[chat_id] = {"participation": False, "track": False, "sections": False, "transport": False}
    bot.clear_step_handler_by_chat_id(chat_id)

    get_all_events()
    event = get_nearest_event()

    if event:
        date, time = format_full_datetime_calendar(event["datetime"])
        bot.send_message(
            chat_id,
            "Привет! На связи Wunder-помощник! Со мной Вы сможете быстро и легко зарегистрироваться на мероприятия международной школы Wunderpark.\n\n"
            f"📅 Ближайшее мероприятие: *{event['name']}*\n\n"
            f"🕒 *Дата мероприятия:* {date} в {time}\n\n"
            "Чтобы стать его участником, ответьте на несколько вопросов. Начнем?\n\n"
            "Как Вас зовут? Укажите, пожалуйста, полное ФИО:",
            parse_mode="Markdown"
        )

        user_data[chat_id]['event'] = event['name']
        bot.register_next_step_handler(message, check_user)

    else:
        bot.send_message(
            chat_id,
            "К сожалению, на данный момент мероприятий не запланировали.",
            parse_mode="Markdown"
        )



# STEP 1: CHECK
def check_user(message):
    """Проверяем был ли пользователь уже зарегистрирован"""
    chat_id = message.chat.id
    user_data[chat_id]['name'] = message.text

    event = user_data[chat_id]['event']

    check_user_registration(user_data[chat_id]['name'], chat_id, event, message)

def check_user_registration(user_name, chat_id, event, message):
    """Сверяем с базой данных наличие пользователя в указанном мероприятии"""
    try:
        connection = pymysql.connect(**db_config)

        with connection.cursor() as cursor:
            sql_check_query = "SELECT id FROM registrations WHERE name = %s AND event = %s"
            cursor.execute(sql_check_query, (user_name, event))
            existing_user = cursor.fetchone()

            if existing_user:
                send_change_data_message(user_name, chat_id)
            else:
                get_phone(message)

    except Exception as e:
        print(f"⚠️ Ошибка при работе с MySQL: {e}")

    finally:
        connection.close()

def send_change_data_message(user_name, chat_id):
    """Если был зарегистрирован, то отправляем сообщение"""
    markup = types.InlineKeyboardMarkup()
    btn_fix = types.InlineKeyboardButton("✅ Да, изменить", callback_data="change_data")
    btn_no_fix = types.InlineKeyboardButton("❌ Нет", callback_data="no_change")
    markup.add(btn_fix, btn_no_fix)

    bot.send_message(chat_id, "Вы уже вводили данные — хотите изменить?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["change_data", "no_change"])
def handle_change_data_response(call):
    """Делаем кнопки неактивными после выбора ответа и переходим к следующему шагу"""
    chat_id = call.message.chat.id

    markup = types.InlineKeyboardMarkup()
    btn_fix = types.InlineKeyboardButton("✅ Да, изменить", callback_data="do_nothing")
    btn_no_fix = types.InlineKeyboardButton("❌ Нет", callback_data="do_nothing")
    markup.add(btn_fix, btn_no_fix)

    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)

    if call.data == "change_data":
        bot.answer_callback_query(call.id, "Введите новые данные.")
        bot.send_message(chat_id, "Тогда давайте начнём с начала.\nУкажите новые имя и фамилию:")
        bot.register_next_step_handler_by_chat_id(chat_id, get_phone)

    elif call.data == "no_change":
        bot.answer_callback_query(call.id, "Вы решили не менять данные.")
        bot.send_message(chat_id, "Хорошо, если вам понадобятся изменения, просто отправьте /start и мы начнём заново!")



# STEP 2
def get_phone(message):
    """Действие бота после ввода имени"""
    chat_id = message.chat.id
    user_data[chat_id]['name'] = message.text

    if is_start_command(message):
        start(message)
        return

    bot.send_message(chat_id, "Приятно познакомиться, {}! Укажите Ваш номер телефона (пример: +70000000000)".format(message.text))
    bot.register_next_step_handler(message, validate_phone)



# STEP 3
def validate_phone(message):
    """Проверяем правильно ли введён номер телефона и переходим к следующему шагу"""
    chat_id = message.chat.id
    phone = message.text.strip()

    if is_start_command(message):
        start(message)
        return

    if re.fullmatch(r'\+7[0-9]{10}', phone):
        user_data[chat_id]['phone'] = phone
        bot.send_message(chat_id, "Спасибо, а теперь укажите Вашу почту:")
        bot.register_next_step_handler(message, validate_email)
    else:
        bot.send_message(chat_id, "❌ Некорректный номер телефона. Формат: +71112223344. Попробуйте еще раз:")
        bot.register_next_step_handler(message, validate_phone)

def validate_email(message):
    """Проверяем правильно ли введена почта и переходим к следующему шагу"""
    chat_id = message.chat.id
    email = message.text.strip()

    if is_start_command(message):
        start(message)
        return

    if re.fullmatch(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', email):
        user_data[chat_id]['email'] = email
        send_participation_options(message)

    else:
        bot.send_message(chat_id, "❌ Некорректный e-mail. Попробуйте еще раз:")
        bot.register_next_step_handler(message, validate_email)



# STEP 4
def send_participation_options(message):
    """Выбор формы участия"""
    chat_id = message.chat.id
    markup = types.InlineKeyboardMarkup()
    btn1 = types.InlineKeyboardButton("Очно", callback_data="Очно")
    btn2 = types.InlineKeyboardButton("Онлайн", callback_data="Онлайн")
    markup.add(btn1, btn2)

    bot.send_message(chat_id, "Пожалуйста, выберите формат участия в конференции:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["Очно", "Онлайн"])
def choose_format(call):
    """Делаем кнопки неактивными после выбора и переходим к следующему шагу"""
    chat_id = call.message.chat.id
    if not user_selections[chat_id]["participation"]:
        user_data[chat_id]['participation'] = call.data
        user_selections[chat_id]["participation"] = True

        markup = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("✅ Очно", callback_data="Очно") if call.data == "Очно" else types.InlineKeyboardButton("Очно", callback_data="Очно")
        btn2 = types.InlineKeyboardButton("✅ Онлайн", callback_data="Онлайн") if call.data == "Онлайн" else types.InlineKeyboardButton("Онлайн", callback_data="Онлайн")
        markup.add(btn1, btn2)

        bot.edit_message_text("Вы выбрали форму участия.", chat_id, call.message.message_id, reply_markup=markup)

        send_track_options(chat_id)
    else:
        bot.answer_callback_query(call.id, "Вы уже выбрали форму участия.")



# STEP 5
def send_track_options(chat_id):
    """Выбор трека"""
    track_markup = types.InlineKeyboardMarkup()
    user_selections[chat_id]["track"] = False
    btn_track1 = types.InlineKeyboardButton("Учительский", callback_data="Учительский")
    btn_track2 = types.InlineKeyboardButton("Родительский", callback_data="Родительский")
    track_markup.add(btn_track1, btn_track2)

    bot.send_message(chat_id, "Укажите, какой трек Вас интересует:", reply_markup=track_markup)

@bot.callback_query_handler(func=lambda call: call.data in ["Учительский", "Родительский"])
def choose_track(call):
    """Делаем кнопки неактивными после выбора и переходим к следующему шагу"""
    chat_id = call.message.chat.id
    if not user_selections[chat_id]["track"]:
        user_data[chat_id]['track'] = call.data
        user_selections[chat_id]["track"] = True

        markup = types.InlineKeyboardMarkup()
        btn_track1 = types.InlineKeyboardButton("✅ Учительский", callback_data="Учительский") if call.data == "Учительский" else types.InlineKeyboardButton("Учительский", callback_data="Учительский")
        btn_track2 = types.InlineKeyboardButton("✅ Родительский", callback_data="Родительский") if call.data == "Родительский" else types.InlineKeyboardButton("Родительский", callback_data="Родительский")
        markup.add(btn_track1, btn_track2)

        bot.edit_message_text("Вы выбрали трек.", chat_id, call.message.message_id, reply_markup=markup)

        send_section_buttons(chat_id)
    else:
        bot.answer_callback_query(call.id, "Вы уже выбрали трек.")



# STEP 6
def generate_callback_data(first_line, second_line):
    """Хеш из данных"""
    section_hash = hashlib.md5(f"{first_line}{second_line}".encode()).hexdigest()[:10]

    if 'sections_data' not in user_data:
        user_data['sections_data'] = {}

    user_data['sections_data'][section_hash] = (first_line, second_line)
    return f"section_{section_hash}"

def generate_button_text(first_line, second_line):
    """Текст копок с сокращённым хешем для уникальности"""
    return f"{first_line} — {second_line}"

def generate_confirm_button_text(first_line, second_line):
    """Текст подтверждённых кнопок с сокращённым хешем для уникальности"""
    return f"✅ {first_line} — {second_line}"


def send_section_buttons(chat_id):
    """Инлайн-кнопки с секциями и их описанием"""
    event = get_nearest_event()
    if event:
        sections = event['description'].strip().split('\n\n')

        teacher_sections = []
        parent_sections = []
        teacher_online_sections = []
        parent_online_sections = []

        category = None
        for section in sections:
            if "(Учительский)" in section:
                category = "Учительский"
            elif "(Родительский)" in section:
                category = "Родительский"
            elif "(Онлайн учительский)" in section:
                category = "Онлайн учительский"
            elif "(Онлайн родительский)" in section:
                category = "Онлайн родительский"

            if category == "Учительский":
                clean_section = section.replace("(Учительский)", "").strip()
                teacher_sections.append(clean_section)
            elif category == "Родительский":
                clean_section = section.replace("(Родительский)", "").strip()
                parent_sections.append(clean_section)
            elif category == "Онлайн учительский":
                clean_section = section.replace("(Онлайн учительский)", "").strip()
                teacher_online_sections.append(clean_section)
            elif category == "Онлайн родительский":
                clean_section = section.replace("(Онлайн родительски)", "").strip()
                parent_online_sections.append(clean_section)

        track = user_data[chat_id].get('track')
        formate = user_data[chat_id].get('participation')
        sections_to_send = []

        if formate == "Онлайн":
            if track == "Учительский":
                sections_to_send = teacher_online_sections
            elif track == "Родительский":
                sections_to_send = parent_online_sections
            else:
                sections_to_send = []

        elif formate == "Очно":
            if track == "Учительский":
                sections_to_send = teacher_sections
            elif track == "Родительский":
                sections_to_send = parent_sections
            else:
                sections_to_send = []


        # Кнопки
        if sections_to_send:
            full_message_text = "Выберите интересующую секцию (можно выбрать несколько):\n\n"
            full_markup = types.InlineKeyboardMarkup(row_width=1)

            for section in sections_to_send:
                section_block = section.split('\n\n')

                for section_stroke in section_block:
                    section_lines = section_stroke.split('\n')

                    if not section_lines:
                        continue

                    first_line = section_lines[0]  # Время и название секции
                    second_line = section_lines[1] if len(section_lines) > 1 else "" # Описание
                    second_line = re.split(r"\s+(?=http)", second_line)[0]

                    if not second_line.strip():
                        continue

                    btn = types.InlineKeyboardButton(
                        generate_button_text(first_line, second_line),
                        callback_data=generate_callback_data(first_line, second_line)
                    )

                    full_markup.add(btn)
                    full_message_text += "\n"

            # Подтверждение выбора секций
            if user_data[chat_id].get('sections', []):
                btn_confirm = types.InlineKeyboardButton("Подтвердить выбор", callback_data="confirm_sections")
                markup = types.InlineKeyboardMarkup()
                markup.add(btn_confirm)

                bot.send_message(
                    chat_id,
                    "Выберите секции и подтвердите свой выбор.",
                    reply_markup=markup
                )

            bot.send_message(
                chat_id,
                full_message_text,
                reply_markup=full_markup,
                parse_mode="HTML"
            )

        else:
            bot.send_message(chat_id, "Секции не найдены для выбранного трека.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("section_"))
def handle_section_selection(call):
    chat_id = call.message.chat.id

    # Проверяем, подтвержден ли уже выбор
    if user_data.get(chat_id, {}).get('sections_confirmed', False):
        bot.answer_callback_query(call.id, "❌ Выбор секций уже подтвержден.", show_alert=True)
        return

    section_hash = call.data.replace("section_", "")

    if 'sections_data' not in user_data or section_hash not in user_data['sections_data']:
        bot.answer_callback_query(call.id, "Ошибка: секция не найдена.")
        return

    first_line, second_line = user_data['sections_data'][section_hash]
    section_full = f"{first_line} — {second_line}"

    if 'sections' not in user_data.setdefault(chat_id, {}):
        user_data[chat_id]['sections'] = []

    if section_full in user_data[chat_id]['sections']:
        user_data[chat_id]['sections'].remove(section_full)
        button_text = generate_button_text(first_line, second_line)
        bot.answer_callback_query(call.id, f"Вы убрали:\n{section_full}")
    else:
        user_data[chat_id]['sections'].append(section_full)
        button_text = generate_confirm_button_text(first_line, second_line)
        bot.answer_callback_query(call.id, f"Вы выбрали:\n{section_full}")

    # Обновляем кнопки
    new_buttons = []
    for button in call.message.reply_markup.keyboard:
        btn = button[0]
        if btn.callback_data == call.data:
            new_buttons.append([types.InlineKeyboardButton(button_text, callback_data=call.data)])
        else:
            new_buttons.append([btn])

    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup(new_buttons))

    # Обновляем кнопку подтверждения
    update_confirmation_button(chat_id)

def update_confirmation_button(chat_id):
    """Обновляет кнопку подтверждения в зависимости от выбранных секций"""
    has_selected = bool(user_data.get(chat_id, {}).get('sections', []))

    if has_selected:
        confirm_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        confirm_markup.add(types.KeyboardButton("✅ Подтвердить выбор"))

        # Удаляем старое сообщение с кнопкой подтверждения, если есть
        if 'confirm_message_id' in user_data.get(chat_id, {}):
            try:
                bot.delete_message(chat_id, user_data[chat_id]['confirm_message_id'])
            except:
                pass

        # Отправляем новое сообщение с кнопкой подтверждения
        msg = bot.send_message(
            chat_id,
            "Нажмите «Подтвердить выбор» для продолжения.",
            reply_markup=confirm_markup
        )
        user_data[chat_id]['confirm_message_id'] = msg.message_id
    else:
        # Если ничего не выбрано
        if 'confirm_message_id' in user_data.get(chat_id, {}):
            try:
                bot.delete_message(chat_id, user_data[chat_id]['confirm_message_id'])
                del user_data[chat_id]['confirm_message_id']
            except:
                pass
            bot.send_message(chat_id, "Выберите секции", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: message.text == "✅ Подтвердить выбор")
def handle_confirm_selection(message):
    chat_id = message.chat.id

    if not user_data.get(chat_id, {}).get('sections'):
        bot.send_message(chat_id, "❌ Нет выбранных секций для подтверждения.")
        return

    # Помечаем выбор как подтвержденный
    user_data[chat_id]['sections_confirmed'] = True

    # Удаляем кнопку подтверждения
    try:
        bot.delete_message(chat_id, message.message_id)
    except:
        pass

    # Делаем все инлайн-кнопки неактивными
    if message.reply_to_message and message.reply_to_message.reply_markup:
        disabled_buttons = []
        for row in message.reply_to_message.reply_markup.keyboard:
            disabled_row = []
            for btn in row:
                disabled_row.append(types.InlineKeyboardButton(
                    text=btn.text,
                    callback_data="disabled",
                    disabled=True
                ))
            disabled_buttons.append(disabled_row)

        try:
            bot.edit_message_reply_markup(
                chat_id,
                message.reply_to_message.message_id,
                reply_markup=types.InlineKeyboardMarkup(disabled_buttons)
            )
        except Exception as e:
            print(f"Error disabling buttons: {e}")

    # Уведомление о подтверждении
    bot.send_message(
        chat_id,
        "✅ Выбор секций подтвержден.",
        reply_markup=types.ReplyKeyboardRemove()
    )

    formate = user_data[chat_id].get('participation')

    try:
        if formate == "Онлайн":
            confirm_data(message)

        elif formate == "Очно":
            select_transport(message)
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "disabled")
def handle_disabled_button(call):
    """Обработчик для заблокированных кнопок"""
    bot.answer_callback_query(call.id, "Выбор секций уже подтвержден.")



# STEP 7
def select_transport(message_or_call):
    """Выбор транспорта"""
    if hasattr(message_or_call, 'message'):
        chat_id = message_or_call.message.chat.id
    else:
        chat_id = message_or_call.chat.id

    if chat_id not in user_data:
        bot.send_message(chat_id, "⚠️ Ошибка: данные пользователя не найдены.")
        return

    markup = types.InlineKeyboardMarkup()

    user_selections[chat_id]["transport"] = False
    btn_track1 = types.InlineKeyboardButton("На такси", callback_data="На такси")
    btn_track2 = types.InlineKeyboardButton("На своём автомобиле", callback_data="На своём автомобиле")
    btn_track3 = types.InlineKeyboardButton("Нужен трансфер от метро Щукинская", callback_data="Нужен трансфер от метро Щукинская")
    btn_track4 = types.InlineKeyboardButton("Нужен трансфер от метро Строгино", callback_data="Нужен трансфер от метро Строгино")

    markup.add(btn_track1)
    markup.add(btn_track2)
    markup.add(btn_track3)
    markup.add(btn_track4)

    bot.send_message(chat_id, "Как будете добираться:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["На такси", "На своём автомобиле", "Нужен трансфер от метро Щукинская", "Нужен трансфер от метро Строгино"])
def choose_transport(call):
    """Делаем кнопки неактивными после выбора и переходим к следующему шагу"""
    chat_id = call.message.chat.id
    if not user_selections[chat_id]["transport"]:
        user_data[chat_id]['transport'] = call.data
        user_selections[chat_id]["transport"] = True

        markup = types.InlineKeyboardMarkup()
        btn_track1 = types.InlineKeyboardButton("✅ На такси", callback_data="На такси") if call.data == "На такси" else types.InlineKeyboardButton("На такси", callback_data="На такси")
        btn_track2 = types.InlineKeyboardButton("✅ На своём автомобиле", callback_data="На своём автомобиле") if call.data == "На своём автомобиле" else types.InlineKeyboardButton("На своём автомобиле", callback_data="На своём автомобиле")
        btn_track3 = types.InlineKeyboardButton("✅ Нужен трансфер от метро Щукинская", callback_data="Нужен трансфер от метро Щукинская") if call.data == "Нужен трансфер от метро Щукинская" else types.InlineKeyboardButton("Нужен трансфер от метро Щукинская", callback_data="Нужен трансфер от метро Щукинская")
        btn_track4 = types.InlineKeyboardButton("✅ Нужен трансфер от метро Строгино", callback_data="Нужен трансфер от метро Строгино") if call.data == "Нужен трансфер от метро Строгино" else types.InlineKeyboardButton("Нужен трансфер от метро Строгино", callback_data="Нужен трансфер от метро Строгино")

        markup.add(btn_track1)
        markup.add(btn_track2)
        markup.add(btn_track3)
        markup.add(btn_track4)

        bot.edit_message_text("Вы выбрали транспорт.", chat_id, call.message.message_id, reply_markup=markup)

        confirm_data(call)
    else:
        bot.answer_callback_query(call.id, "Вы уже выбрали транспорт.")



# STEP 8
def confirm_data(message_or_call):
    """Подтверждение данных"""
    if hasattr(message_or_call, 'message'):
        chat_id = message_or_call.message.chat.id
    else:
        chat_id = message_or_call.chat.id

    if chat_id not in user_data:
        bot.send_message(chat_id, "⚠️ Ошибка: данные пользователя не найдены.")
        return

    event = get_nearest_event()
    if not event:
        bot.send_message(chat_id, "⚠️ Ошибка: мероприятие не найдено.")
        return

    name = event["name"]
    location = event["location"]
    date, time = format_datetime_calendar(event["datetime"])

    try:
        sections_text = "\n".join(user_data[chat_id].get('sections', [])) if 'sections' in user_data[chat_id] else "Не выбрано"

        formate = user_data[chat_id].get('participation')
        transport = ''
        data_text = ''

        if formate == "Онлайн":
            transport = ''

            data_text = (
                f"📋 <u>Проверьте введённые данные:</u>\n\n"
                f"<b>Имя:</b> {user_data[chat_id]['name']}\n"
                f"<b>Телефон:</b> {user_data[chat_id]['phone']}\n"
                f"<b>E-mail:</b> {user_data[chat_id]['email']}\n\n"
                f"<b>Форма участия:</b> {user_data[chat_id]['participation']}\n"
                f"<b>Трек:</b> {user_data[chat_id]['track']}\n\n"
                f"<b>Секции:</b> \n{sections_text}\n\n"
                f"<b>Вcё верно?</b>"
            )

        elif formate == "Очно":
            transport = user_data[chat_id]['transport']

            data_text = (
                f"📋 <u>Проверьте введённые данные:</u>\n\n"
                f"<b>Имя:</b> {user_data[chat_id]['name']}\n"
                f"<b>Телефон:</b> {user_data[chat_id]['phone']}\n"
                f"<b>E-mail:</b> {user_data[chat_id]['email']}\n\n"
                f"<b>Форма участия:</b> {user_data[chat_id]['participation']}\n"
                f"<b>Трек:</b> {user_data[chat_id]['track']}\n\n"
                f"<b>Секции:</b> \n{sections_text}\n\n"
                f"<b>Транспорт:</b> {user_data[chat_id]['transport']}\n\n"
                f"<b>Вcё верно?</b>"
            )

        # FOR DB
        user_data_entry = {
            'name': user_data[chat_id]['name'],
            'phone': user_data[chat_id]['phone'],
            'email': user_data[chat_id]['email'],
            'participation': user_data[chat_id]['participation'],
            'track': user_data[chat_id]['track'],
            'sections': sections_text,
            'status': 'pending',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'chat_id': chat_id,
            'event': name,
            'id': chat_id,
            'location': location,
            'date_event': date,
            'time_event': time,
            'transport': transport
        }

        # SAVE TO DB
        update_user_data(user_data_entry)

        markup = types.InlineKeyboardMarkup()
        btn_yes = types.InlineKeyboardButton("Да, подтвердить", callback_data="confirm")
        btn_no = types.InlineKeyboardButton("Изменить", callback_data="restart")
        markup.add(btn_yes, btn_no)

        bot.send_message(chat_id, data_text, reply_markup=markup, parse_mode="HTML")

    except KeyError as e:
        bot.send_message(chat_id, f"⚠️ Ошибка: отсутствует ключ в данных пользователя: {e}")
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка: {e}")



# STEP 9
@bot.callback_query_handler(func=lambda call: call.data in ["confirm", "restart"])
def confirmation_handler(call):
    """Действие на подтверждение/изменение данных и согласие на обработку персональных данных"""
    chat_id = call.message.chat.id

    markup = types.InlineKeyboardMarkup()
    btn_yes = types.InlineKeyboardButton("✅ Да,подтвердить", callback_data="do_nothing")
    btn_no = types.InlineKeyboardButton("❌ Изменить", callback_data="do_nothing")
    markup.add(btn_yes, btn_no)

    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)

    # START OVER
    if call.data == "restart":
        user_data[chat_id] = {}
        user_selections[chat_id] = {"participation": False, "track": False, "sections": False, "transport": False}
        bot.answer_callback_query(call.id, "Введите новые данные.")
        bot.send_message(chat_id, "Тогда давайте начнём с начала.\nУкажите новые имя и фамилию:")
        bot.register_next_step_handler_by_chat_id(chat_id, get_phone)
        return

    # CONFIRM
    elif call.data == "confirm":
        bot.answer_callback_query(call.id, "Вы подтвердили данные.")

        # CONFIDENTIALITY POLICY
        markup = types.InlineKeyboardMarkup()
        btn_agree = types.InlineKeyboardButton("Согласен", callback_data="agree")
        btn_policy = types.InlineKeyboardButton("📄 Политика конфиденциальности", url="https://wunderpark.ru/polz_soglashenie/")
        markup.add(btn_policy)
        markup.add(btn_agree)

        bot.send_message(
            chat_id,
            "Последний шаг! Чтобы мы могли присылать Вам уведомления о конференции, подтвердите согласие на обработку персональных данных.\n\n"
            "Я даю согласие Wunderpark International School и его партнёрам на обработку персональных данных на условиях Политики конфиденциальности в целях регистрации моего участия в мероприятиях Wunderpark и получения информационных сообщений о них.",
            reply_markup=markup
        )



# STEP 10
@bot.callback_query_handler(func=lambda call: call.data == "agree")
def final_confirmation(call):
    """Обновление данных и уведомление об успешной регистрации"""
    chat_id = call.message.chat.id

    markup = types.InlineKeyboardMarkup()
    btn_agree = types.InlineKeyboardButton("✅ Согласен", callback_data="do_nothing")
    btn_policy = types.InlineKeyboardButton("📄 Политика конфиденциальности", url="https://example.com")
    markup.add(btn_policy)
    markup.add(btn_agree)

    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id, "Вы дали согласие на обработку персональных данных.")

    try:
        event = get_nearest_event()
        if event:
            name = event["name"]
            location = event["location"]
            date, time = format_datetime_calendar(event["datetime"])

            formate = user_data[chat_id].get('participation')
            transport = ''

            if formate == "Онлайн":
                transport = ''

            elif formate == "Очно":
                transport = user_data[chat_id]['transport']

            update_user_data({
                'name': user_data[chat_id]['name'],
                'phone': user_data[chat_id]['phone'],
                'email': user_data[chat_id]['email'],
                'participation': user_data[chat_id]['participation'],
                'track': user_data[chat_id]['track'],
                'sections': ", ".join(user_data[chat_id]['sections']),
                'status': 'Confirmed',
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'chat_id': chat_id,
                'event': name,
                'id': chat_id,
                'location': location,
                'date_event': date,
                'time_event': time,
                'transport': transport
            })

    except Exception as e:
        print(f"Ошибка обновления данных: {e}")
        bot.send_message(chat_id, "⚠️ Ошибка при обновлении данных. Попробуйте позже.")
        return

    event = get_nearest_event()

    # FINAL TEXT
    if event:
        maps_link = get_yandex_maps_link(event['location'])
        markup = types.InlineKeyboardMarkup()
        btn_map = types.InlineKeyboardButton("Найти на карте", url=maps_link)
        markup.add(btn_map)

        date, time = format_full_datetime_calendar(event["datetime"])
        formate = user_data[chat_id].get('participation')

        # Выбираем секции в зависимости от формата
        if formate == "Онлайн":
            bot.send_message(
                chat_id,
                f"Спасибо, что решили присоединиться к нашей Wunder-конференции!\n\n"
                f"В день мероприятия я пришлю Вам ссылку на выбранные Вами онлайн-трансляции.\n\n"
                f"Напомню, это будет *{date}*. Начало события: *{time}*\n\n"
                f"Отличного дня и хорошего настроения!",
                parse_mode="Markdown")

        elif formate == "Очно":
            bot.send_message(
                chat_id,
                f"Спасибо, что решили присоединиться к нашей Wunder-конференции!\n\n"
                f"Ждем Вас *{date}* в *{time}* в *{event["location"]}*. \n"
                f"Приходите на конференцию в приятной компании — пригласите с собой друзей и коллег, ведь вместе всегда интереснее.\n\n"
                f"Все подробности я расскажу Вам позже отдельным сообщением. А пока предлагаю посмотреть, как нас найти:\n\n",
                parse_mode="Markdown", reply_markup=markup)



# INACTIVE BUTTONS
@bot.callback_query_handler(func=lambda call: call.data == "do_nothing")
def handle_inactive_buttons(call):
    """Делаем кнопки неактивными и показываем уведомление об этом"""
    if call.message.reply_markup and call.message.reply_markup.keyboard:
        for row in call.message.reply_markup.keyboard:
            for button in row:
                if "✅ Согласен" in button.text:
                    bot.answer_callback_query(call.id, "Вы дали согласие на обработку персональных данных.")
                    return
                elif "✅ Да, подтвердить" in button.text:
                    bot.answer_callback_query(call.id, "Вы уже подтвердили данные.")
                    return
                elif "❌ Изменить" in button.text:
                    bot.answer_callback_query(call.id, "Введите новые данные.")
                    return
                elif "✅ Да, изменить" in button.text:
                    bot.answer_callback_query(call.id, "Вы уже сделали выбор. Начните заново, если хотите изменить.")
                    return
                elif "❌ Нет" in button.text:
                    bot.answer_callback_query(call.id, "Вы уже сделали выбор. Начните заново, если хотите изменить.")
                    return



# CHECK DAY FOR NOTIFICATION AND SURVEY
schedule.every(30).minutes.do(send_event_surveys)
schedule.every(4).hours.do(send_event_reminders)
threading.Thread(target=schedule_checker, daemon=True).start()




bot.polling(none_stop=True)
