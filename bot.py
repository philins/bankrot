from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, Job
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
import logging
import psycopg2
import psycopg2.extras
import urllib.parse
import urllib.request
import json
import datetime

TOKEN = '275614248:AAFNfWAaDqfswl0V2oH7_QeBBt0KVqhQouU'
APIKEY = 'f2fc7983-862c-4752-a0fb-07d1b2900684'
LIST_ST = 5
LIST_TR = 3
limit = 3
users = {}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def log_params(method_name, update):
    logger.debug("Method: %s\nFrom: %s\nchat_id: %d\nText: %s" %
                 (method_name,
                  update.message.from_user,
                  update.message.chat_id,
                  update.message.text))


# def botlog(user_id, first_name, last_name, username, last_station, last_query, transport_types, day):
#     now = datetime.datetime.now()
#     with psycopg2.connect("dbname='botdb' user='bot' host='localhost' password='fresher88'") as db:
#         cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
#         cur.execute(
#             """INSERT INTO "public"."botlog" (date_time, user_id, user_firstname, user_lastname, user_username, station, query, transport_type, day)
#             VALUES('{}','{}','{}','{}','{}','{}','{}','{}','{}')""".format(now, user_id, first_name, last_name, username, last_station, last_query, transport_types, day))


class UserInfo:
    def __init__(self, user):
        self.user = user
        self.transport_types='suburban'
        self.last_station = 0
        self.last_query = ''
        self.job = None
        self.day = 'сегодня'

    def __str__(self):
        return 'User={}, ' \
               'last_station={}, ' \
               'last_query={}, ' \
               'transport_types={}, ' \
               'day={}'.format(self.user,
                               self.last_station,
                               self.last_query,
                               self.transport_types,
                               self.day)

    def addstation(self, code):
        self.last_station = code

    def set_query(self, text):
        self.last_query = text

    def setjob(self, job):
        self.job = job

    def setday(self, day):
        self.day = day


class Station:
    def __init__(self, txt, code, name):
        self.txt = txt
        self.code = code
        self.name = name

def error_callback(bot, update, error):
    print(error)

def keyrenew(code):
    """
    Формирует кнопку для обновления расписания
    Args:
        code: код станции int

    Returns: объект кнопка "Обновить"

    """
    key=[]
    key.append([InlineKeyboardButton(text='Обновить', callback_data=str(code))])
    return InlineKeyboardMarkup(key)


def job_button(bot, job):
    bot.sendMessage(chat_id=job.context[0],
                    text='Расписание по станции ' + basecode(job.context[1].last_station)['title'] + ' устарело.',
                    reply_markup=keyrenew(job.context[1].last_station))


def basename(name):
    """
    Поиск в базе по названию
    Args:
        name: Название или часть названия

    Returns:
    List of codes
    """
    tmpcode = []
    with psycopg2.connect("dbname='botdb' user='bot' host='localhost' password='fresher88'") as db:
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        for modname in [name, name + '%', '%' + name + '%']:
            cur.execute(
                """SELECT code FROM ya_station WHERE transport_type= 'train' AND title iLIKE '{}'""".format(modname))
            rows = cur.fetchall()
            for row in rows:
                if row['code'] not in tmpcode:
                    tmpcode.extend(row)
    return tmpcode

def basecode(code):
    """
    Возвращает строку со станцией из базы
    Args:
        code: Код станции int

    Returns:
    Dict from Row
    """
    with psycopg2.connect("dbname='botdb' user='bot' host='localhost' password='fresher88'") as db:
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            """SELECT * FROM ya_station WHERE code= '{}'""".format(code))
    rows = cur.fetchone()
    return dict(rows)


def keytext(station):
    icon = {'train': '\U0001f68a', 'bus': '\U0001f68c', 'plane': '\u2708\ufe0f', 'sea': '\u26f4', 'river': '\U0001f6e5'}
    return icon[station['transport_type']] + ' ' + station['title'] + ' ' + station['station_type']


def get_rasp(yaid, types, day = 'сегодня'):
    """
    Запрос расписания по станции у Яндекса
    Args:
        yaid: код станции int
        types: transport_types str

    Returns:

    """
    if day == 'сегодня':
        today = datetime.date.today()
    else:
        today = datetime.date.today() + datetime.timedelta(days=1)
    #logger.debug(today)
    now = datetime.datetime.now().timestamp()
    rasp = ''
    retrasp={}
    has_next = True
    page = 1
    trains = []
    while has_next:
        fparams = urllib.parse.urlencode(
            {'apikey': APIKEY, "station": "s" + str(yaid), "date": today, "page": str(page), "format": "json",
             "lang": "ru", "direction": "all", "transport_types": types})
        furl = "https://api.rasp.yandex.net/v1.0/schedule/?" + fparams
        with urllib.request.urlopen(furl) as f:
            rd = f.read().decode()
        data = json.loads(rd)
        has_next = data['pagination']['has_next']
        trains.extend(data['schedule'])
        page += 1

    mintime = 24 * 3600
    for dir in data['directions']:
        if dir in ['all', 'arrival']:
            continue
        rasp += '\n\u27a1\ufe0f ' + dir + '\n'
        counter = 0
        for train in trains:
            if dir == train['direction']:
                dtime = datetime.datetime.strptime(train['departure'], '%Y-%m-%d %H:%M:%S').timestamp() - now
                if dtime < 0:
                    continue
                mintime = dtime if dtime < mintime else mintime
                departure = datetime.datetime.strftime(
                    datetime.datetime.strptime(train['departure'], '%Y-%m-%d %H:%M:%S'), "%H:%M")
                title = train['thread']['short_title'] if train['thread']['short_title'] != '' else train['thread'][
                    'title']
                rasp += "<b>" + departure + "</b> " + title + " <i>" + train['stops'] + "</i>\n"
                counter += 1
                if counter == limit:
                    break
        if counter == 0:
            rasp += 'На ' + day + ' поездов больше нет.\n'
    retrasp['rasp'] = rasp
    retrasp['mintime'] = mintime
    #logger.debug(retrasp)
    return retrasp


def echo(bot, update, job_queue):
    """
    Принимает сообщения из чата:
    - Название или часть названия станции
    Args:
        bot:
        update:
        job_queue:

    Returns:

    """
    log_params('echo', update)
    #logger.debug(update.message.date)
    stname = update.message.text
    telegram_user = update.message.from_user
    if telegram_user.id not in users:
        users[telegram_user.id] = UserInfo(telegram_user)
    user = users[telegram_user.id]
    if 'сегодня' in stname:
        user.setday('сегодня')
        stname = stname.replace('сегодня', '').strip()
    if 'завтра' in stname:
        user.setday('завтра')
        stname = stname.replace('завтра', '').strip()
    if len(stname)>2:
        user.set_query(stname)
        stname=user.last_query
        out = basename(stname)
    elif user.last_station:
        out = [user.last_station]
    else:
        update.message.reply_text('Отправьте мне название станции.')
    if user.job:
        user.job.schedule_removal()

    if len(out) == 0: # not out
        ret = "По вашему запросу станции не найдены.\nВводите название на русском языке.\nПопробуйте ввести часть названия.\nЕ и Ё это разные буквы."
        update.message.reply_text(ret)
        logger.warning(ret)

    elif len(out) != 1:
        ret = "Найдено: " + str(len(out)) + "\n"
        keyboard = []
        for _, line in zip(range(LIST_ST), out):
            station = basecode(line)
            keyboard.append([InlineKeyboardButton(text=keytext(station), callback_data=str(station['code']))])
        if len(out) > len(keyboard):
            keyboard.append([InlineKeyboardButton(text='ещё...', callback_data='1')])
        reply_markup = InlineKeyboardMarkup(keyboard)

        update.message.reply_text(ret, reply_markup=reply_markup)
        logger.info(ret)

    else:
        user.addstation(out[0])
        station = basecode(user.last_station)
        rasp = get_rasp(user.last_station, user.transport_types, user.day)
        returntext = keytext(station) + ' на ' + user.day + ':\n' + rasp['rasp']
        bot.sendMessage(chat_id=update.message.chat_id,
                        text=returntext,
                        parse_mode=ParseMode.HTML)
        logger.info(returntext)
        job_star = Job(job_button,
                       rasp['mintime'],
                       repeat=False,
                       context=[update.message.chat_id, user])
        user.setjob(job_star)
        job_queue.put(job_star)
    logger.debug(user)
    # botlog(user.user.id,
    #        user.user.first_name,
    #        user.user.last_name,
    #        user.user.username,
    #        user.last_station,
    #        user.last_query,
    #        user.transport_types,
    #        user.day)


def button(bot, update, job_queue):
    query = update.callback_query
    keyboard = []
    telegram_user = query.from_user
    user = users[telegram_user.id]
    if user.job:
        user.job.schedule_removal()
    data = int(query.data)
    out = basename(user.last_query)
    if data < 100:
        for i in range(LIST_ST):
            try:
                line = out[i + LIST_ST * data]
            except IndexError:
                break
            station = basecode(line)
            keyboard.append([InlineKeyboardButton(text=keytext(station), callback_data=str(station['code']))])
        if len(out) - LIST_ST * int(query.data) > len(keyboard):
            keyboard.append([InlineKeyboardButton(text='ещё...', callback_data=str(data + 1))])
        reply_markup = InlineKeyboardMarkup(keyboard)
        vse = str(len(out))
        ot = str(LIST_ST * data+1)
        do = vse if int(vse) < LIST_ST * (data+1) else str(LIST_ST * (data+1))
        bot.editMessageText(chat_id=query.message.chat_id,
                            message_id=query.message.message_id,
                            text="Показано: " + ot + ' - ' + do + ' из ' + vse + "\n",
                            reply_markup=reply_markup)
    elif data < 2000000:
        logger.error(data)
        bot.editMessageText(chat_id=query.message.chat_id,
                            message_id=query.message.message_id,
                            text='Вы не устали? Наберите побольше букв.')
    else:
        user.addstation(query.data)
        station = basecode(user.last_station)
        rasp = get_rasp(user.last_station, user.transport_types, user.day)
        returntext = keytext(station) + ' на ' + user.day + ':\n' + rasp['rasp']
        bot.editMessageText(text=returntext,
                            chat_id=query.message.chat_id,
                            message_id=query.message.message_id,
                            parse_mode=ParseMode.HTML)
        logger.info(returntext)
        job_star = Job(job_button,
                       rasp['mintime'],
                       repeat=False,
                       context=[query.message.chat_id, user])
        user.setjob(job_star)
        job_queue.put(job_star)
    logger.debug(user)




def start(bot, update):
    update.message.reply_text('Здравствуйте, {}!\n'
                              'Я робот по поиску расписаний электричек \U0001f68a по всей России.\n'
                              'Подробные инструкции по команде /help \n'
                              'Какую станцию вам найти?'.format(update.message.from_user.first_name))


def help(bot, update):
    update.message.reply_text("""Для поиска расписания по станции отправьте мне название этой станции.
Я выведу по три ближайших электрички по каждому направлению.
Если на сегодня поездов больше нет, или вам нужны позда отправляющиеся после полуночи,
отправьте мне слово "завтра" и я покажу по три электрички отправляющиеся с 00:00 часов.
С этого момента я буду и по другим станциям показывать расписание на завтра.
Чтобы вернуться к просмотру расписания на сегодня, отправьте мне слово "сегодня".
Кстати можно совмещать, например: "выхино завтра" или "лобня сегодня".
""")


# def echo(bot, update):
#     log_params('echo', update)
#     find_station(update.message.text)
#     #bot.sendMessage(chat_id=update.message.chat_id, text=find_station(update.message.text),parse_mode=telegram.ParseMode.HTML)

def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('help', help))
    dp.add_handler(MessageHandler(Filters.text, echo, pass_job_queue=True))
    dp.add_handler(CallbackQueryHandler(button, pass_job_queue=True))
    dp.add_error_handler(error_callback)
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
