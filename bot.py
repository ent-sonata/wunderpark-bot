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
    """Конвертирования даты в нужный формат для календаря"""
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



# CHECK COMMAND START
def is_start_command(message):
    """Проверяем была ли отправлена команде /start"""
    return message.text and message.text.startswith('/start')



# UPDATE USERS
def update_user_data(user):
    """Добавление/обновление пользователей в БД"""
    try:
        connection = pymysql.connect(**db_config)

        with connection.cursor() as cursor:
            sql_check_query = "SELECT id FROM registrations WHERE name = %s AND event = %s"
            cursor.execute(sql_check_query, (user['name'], user['event']))
            existing_user = cursor.fetchone()

            if existing_user:
                sql_update_query = """
                UPDATE registrations 
                SET phone = %s, email = %s, participation = %s, track = %s, sections = %s, 
                    status = %s, chat_id = %s, location = %s, date_event = %s, time_event = %s 
                WHERE name = %s AND event = %s
                """
                data_tuple = (
                    user['phone'],
                    user['email'],
                    user['participation'],
                    user['track'],
                    user['sections'],
                    user['status'],
                    user['chat_id'],
                    user['location'],
                    user['date_event'],
                    user['time_event'],
                    user['name'],
                    user['event']
                )
                cursor.execute(sql_update_query, data_tuple)
                print(f"✅ Данные пользователя {user['name']} обновлены для события '{user['event']}'.")
            else:
                sql_insert_query = """
                INSERT INTO registrations (name, phone, email, participation, track, sections, status, created_at, chat_id, event, location, date_event, time_event)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    user['time_event']
                )
                cursor.execute(sql_insert_query, data_tuple)
                print(f"✅ Новый пользователь {user['name']} добавлен для события '{user['event']}'.")

            connection.commit()

    except Exception as e:
        print(f"⚠️ Ошибка при работе с MySQL: {e}")
        print(f"Данные, вызвавшие ошибку: {user}")

    finally:
        if 'connection' in locals() and connection:
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



# GET CHAT ID AND USER STATUS
def get_check_values():
    """Получаем айди чата в боте и статус регистрации пользователя"""
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute("SELECT chat_id, status FROM registrations")
    chat_data = [(row[0], row[1]) for row in cursor.fetchall()]

    conn.close()
    return chat_data



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

        if label in ["week"]:
            message = (f"Информируем, что совсем скоро будет проходить мероприятие, на которое Вы зарегистрировались:\n\n"
                       f"*{event['name']}*\n\n"
                       f"📅 *Дата:* {date}\n\n"
                       f"🕒 *Время:* {time}\n\n"
                       f"📍 *Место:* {event['location']}")

        elif label in ["one_day"]:
            message = (f"Уже завтра мероприятие *{event['name']}!*\n\n"
                       f"🕒 *Время:* {time}\n\n"
                       f"📍 *Место:* {event['location']}")

        maps_link = get_yandex_maps_link(event['location'])
        markup = types.InlineKeyboardMarkup()
        btn_map = types.InlineKeyboardButton("Посмотреть на карте", url=maps_link)
        markup.add(btn_map)

        for chat_id in confirmed_chat_ids:
            try:
                bot.send_message(chat_id, message, reply_markup=markup, parse_mode="Markdown")
            except Exception as e:
                print(f"Ошибка при отправке сообщения пользователю {chat_id}: {e}")

def send_event_reminders():
    """Проверяем, есть ли события, которые начинаются через 7 дней, 1 день или 10 минут"""
    get_all_events()
    event = get_nearest_event()

    if event:
        now = datetime.now(timezone.utc)
        reminder_intervals = {
            "week": timedelta(days=7),
            "one_day": timedelta(days=1),
            "test_second": timedelta(minutes=10)
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
    user_selections[chat_id] = {"participation": False, "track": False, "sections": False}
    bot.clear_step_handler_by_chat_id(chat_id)

    get_all_events()
    event = get_nearest_event()

    if event:
        date, time = format_datetime_calendar(event["datetime"])
        bot.send_message(
            chat_id,
            "Добро пожаловать на регистрацию мероприятий Wunderpark! 🎉\n\n"
            f"📅 Ближайшее мероприятие:\n"
            f"— *{event['name']} ({date} в {time})*\n\n"
            f"📍 Место проведения:\n"
            f"— *{event['location']}*\n\n"
            "Пожалуйста, введите Ваше полное имя, если хотите записаться:",
            parse_mode="Markdown"
        )

        user_data[chat_id]['event'] = event['name']

    else:
        bot.send_message(
            chat_id,
            "К сожалению, на данный момент мероприятий не запланировали.",
            parse_mode="Markdown"
        )

    bot.register_next_step_handler(message, check_user)



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

    bot.send_message(chat_id, "Вы уже зарегистрированы на мероприятие — хотите изменить данные?", reply_markup=markup)

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

    bot.send_message(chat_id, "Отлично, {}!\nТеперь укажите, пожалуйста, свой номер телефона:".format(message.text))
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
        bot.send_message(chat_id, "Спасибо! Так же нам нужно знать Ваш e-mail:")
        bot.register_next_step_handler(message, validate_email)
    else:
        bot.send_message(chat_id, "❌ Некорректный номер телефона. Формат: +71112223344. Попробуйте еще раз:")
        bot.register_next_step_handler(message, validate_phone)

def validate_email(message):
    """Проверяем правильно введена почта и переходим к следующему шагу"""
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

    bot.send_message(chat_id, "Выберите форму участия:", reply_markup=markup)

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

    bot.send_message(chat_id, "Выберите интересующий Вас трек:", reply_markup=track_markup)

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

        # FACE-TO-FACE
        if user_data[chat_id]['participation'] == "Очно":
            send_section_buttons(chat_id)

        # ONLINE
        else:
            confirm_data(call)
    else:
        bot.answer_callback_query(call.id, "Вы уже выбрали трек.")



# STEP 6
def send_section_buttons(chat_id):
    """Выбор секций мероприятия"""
    event = get_nearest_event()
    if event:
        sections = event['description'].strip().split('\n')

        markup = types.InlineKeyboardMarkup()

        for section in sections:
            is_selected = "✅" if section in user_data[chat_id].get('sections', []) else ""
            btn = types.InlineKeyboardButton(
                f"{is_selected} {section}",
                callback_data=section
            )
            markup.add(btn)

        if user_data[chat_id].get('sections', []):
            btn_confirm = types.InlineKeyboardButton("✅ Подтвердить выбор", callback_data="confirm_sections")
            markup.add(btn_confirm)

        bot.send_message(
            chat_id,
            "Отметьте секции, которые хотите посетить (можно выбрать несколько):",
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: call.data in [section for section in get_nearest_event()['description'].strip().split('\n')])
def handle_section_selection(call):
    """Логика кнопок, как чекбоксов и появление/скрытие кнопки «Подтвердить»"""
    chat_id = call.message.chat.id

    if user_data[chat_id].get('sections_confirmed', False):
        bot.answer_callback_query(call.id, "❌ Выбор секций уже подтвержден.")
        return

    section = call.data

    if 'sections' not in user_data[chat_id]:
        user_data[chat_id]['sections'] = []

    if section in user_data[chat_id]['sections']:
        user_data[chat_id]['sections'].remove(section)
    else:
        user_data[chat_id]['sections'].append(section)

    event = get_nearest_event()
    if event:
        sections = event['description'].strip().split('\n')

        markup = types.InlineKeyboardMarkup()
        for section in sections:
            is_selected = "✅" if section in user_data[chat_id]['sections'] else ""
            btn = types.InlineKeyboardButton(
                f"{is_selected} {section}",
                callback_data=section
            )
            markup.add(btn)

        if user_data[chat_id]['sections']:
            btn_confirm = types.InlineKeyboardButton(
                "✅ Подтвердить выбор" if user_data[chat_id].get('sections_confirmed', False) else "Подтвердить выбор",
                callback_data="confirm_sections"
            )
            markup.add(btn_confirm)

        bot.edit_message_text(
            "Отметьте секции, которые хотите посетить (можно выбрать несколько):",
            chat_id,
            call.message.message_id,
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: call.data == "confirm_sections")
def confirm_sections(call):
    """Действие при подтверждении выбора секций и переход к следующему шагу"""
    chat_id = call.message.chat.id

    if 'sections' in user_data[chat_id] and user_data[chat_id]['sections']:
        user_data[chat_id]['sections_confirmed'] = True

        markup = types.InlineKeyboardMarkup()
        event = get_nearest_event()
        if event:
            sections = event['description'].strip().split('\n')

            for section in sections:
                btn = types.InlineKeyboardButton(
                    f"✅ {section}" if section in user_data[chat_id]['sections'] else section,
                    callback_data="section_already_chosen"
                )
                markup.add(btn)

        btn_confirm = types.InlineKeyboardButton("✅ Подтвердить выбор", callback_data="do_nothing")
        markup.add(btn_confirm)

        bot.edit_message_text(
            "Выбор секций подтверждён.",
            chat_id,
            call.message.message_id,
            reply_markup=markup
        )

        confirm_data(call)
    else:
        bot.answer_callback_query(call.id, "❌ Выберите хотя бы одну секцию.")

@bot.callback_query_handler(func=lambda call: call.data == "section_already_chosen")
def handle_inactive_sections(call):
    """Делаем неактивными кнопки, если секции были подтверждены"""
    chat_id = call.message.chat.id

    if user_data[chat_id].get('sections_confirmed', False):
        bot.answer_callback_query(call.id, "Секции уже были выбраны.")
    else:
        pass



# STEP 7
def confirm_data(call):
    """Подтверждение данных"""
    chat_id = call.message.chat.id

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
        # FACE-TO-FACE
        if user_data[chat_id]['participation'] == "Очно":
            sections_text = "\n".join(user_data[chat_id]['sections']) if 'sections' in user_data[chat_id] else "Не выбрано"

            data_text = (
                f"📋 <u>Проверьте введенные данные:</u>\n\n"
                f"<b>Имя:</b> {user_data[chat_id]['name']}\n"
                f"<b>Телефон:</b> {user_data[chat_id]['phone']}\n"
                f"<b>E-mail:</b> {user_data[chat_id]['email']}\n\n"
                f"<b>Форма участия:</b> {user_data[chat_id]['participation']}\n"
                f"<b>Трек:</b> {user_data[chat_id]['track']}\n\n"
                f"<b>Секции:</b> \n{sections_text}\n\n"
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
                'time_event': time
            }

        # ONLINE
        else:
            data_text = (
                f"📋 <u>Проверьте введенные данные:</u>\n\n"
                f"<b>Имя:</b> {user_data[chat_id]['name']}\n"
                f"<b>Телефон:</b> {user_data[chat_id]['phone']}\n"
                f"<b>E-mail:</b> {user_data[chat_id]['email']}\n\n"
                f"<b>Форма участия:</b> {user_data[chat_id]['participation']}\n"
                f"<b>Трек:</b> {user_data[chat_id]['track']}\n\n"
                f"<b>Всё верно?</b>"
            )

            # FOR DB
            user_data_entry = {
                'name': user_data[chat_id]['name'],
                'phone': user_data[chat_id]['phone'],
                'email': user_data[chat_id]['email'],
                'participation': user_data[chat_id]['participation'],
                'track': user_data[chat_id]['track'],
                'sections': '',
                'status': 'pending',
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'chat_id': chat_id,
                'event': name,
                'id': chat_id,
                'location': location,
                'date_event': date,
                'time_event': time
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



# STEP 8
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
        user_selections[chat_id] = {"participation": False, "track": False, "sections": False}
        user_name = user_data[chat_id].get('name', '')
        get_phone(user_name, call.message)
        return

    # CONFIRM
    elif call.data == "confirm":
        bot.answer_callback_query(call.id, "Вы подтвердили данные.")

        # CONFIDENTIALITY POLICY
        markup = types.InlineKeyboardMarkup()
        btn_agree = types.InlineKeyboardButton("Согласен", callback_data="agree")
        btn_policy = types.InlineKeyboardButton("📄 Политика конфиденциальности", url="https://example.com")
        markup.add(btn_policy)
        markup.add(btn_agree)

        bot.send_message(
            chat_id,
            "Последний шаг! Чтобы мы могли присылать Вам уведомления о конференции, подтвердите согласие на обработку персональных данных.\n\n"
            "Я даю согласие Wunderpark International School и его партнёрам на обработку персональных данных на условиях Политики конфиденциальности в целях регистрации моего участия в мероприятиях Wunderpark и получения информационных сообщений о них.",
            reply_markup=markup
        )



# STEP 9
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

            # UPDATE DB FOR FACE-TO-FACE
            if user_data[chat_id]['participation'] == "Очно":
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
                    'time_event': time
                })

            # UPDATE DB FOR ONLINE
            else:
                update_user_data({
                    'name': user_data[chat_id]['name'],
                    'phone': user_data[chat_id]['phone'],
                    'email': user_data[chat_id]['email'],
                    'participation': user_data[chat_id]['participation'],
                    'track': user_data[chat_id]['track'],
                    'sections': '',
                    'status': 'confirmed',
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'chat_id': chat_id,
                    'event': name,
                    'id': chat_id,
                    'location': location,
                    'date_event': date,
                    'time_event': time
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
        btn_map = types.InlineKeyboardButton("Посмотреть на карте", url=maps_link)
        markup.add(btn_map)

        date, time = format_datetime_calendar(event["datetime"])

        bot.send_message(
            chat_id,
            "🎉 Спасибо за регистрацию!\n\n"
            f"Вы записались на мероприятие:\n"
            f"— *{event["name"]}*\n\n"
            f"Мероприятие пройдёт:\n\n"
            f"🕓 *{date} в {time}*\n\n"
            f"📍 *{event["location"]}*\n\n",
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
schedule.every().day.at("19:00").do(send_event_reminders)
threading.Thread(target=schedule_checker, daemon=True).start()



bot.polling(none_stop=True)
