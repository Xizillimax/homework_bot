import logging
import os
import time

import requests
import telegram
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

from exceptions import ApiAnsverError, RequestsError, StatusError

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler('my_log.log',
                              maxBytes=50000000,
                              backupCount=5)
logger.addHandler(handler)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

ONE_DAY_IN_SECONDS = 86400
RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет токены на наличие."""
    all_tokens = {'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
                  'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
                  'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID}
    broken_tokens = []
    for token, value in all_tokens.items():
        if value is None:
            broken_tokens.append(token)
    if broken_tokens:
        message = ('Отсутствие обязательных переменных'
                   'окружения во время запуска бота: '
                   f"{', '.join([i for i in broken_tokens])}")
        logging.critical(message, exc_info=True)
        return False
    return True


def send_message(bot, message):
    """Отправляет сообщения."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception:
        logging.error('сбой при отправке сообщения в Telegram', exc_info=True)
    else:
        logging.debug('удачная отправка любого сообщения в Telegram',
                      exc_info=True)


def get_api_answer(timestamp):
    """Получает данные с сайта и проверяет их."""
    params = {
        'from_date': timestamp
    }
    try:
        api_answer = requests.get(ENDPOINT, params=params, headers=HEADERS)
    except requests.RequestException as error:
        message = f'Ошибка при отправке запроса: {error}'
        raise RequestsError(message)
    if api_answer.status_code != 200:
        message = 'Любые другие сбои при запросе к эндпоинту'
        raise ApiAnsverError(message)
    try:
        api_answer_json = api_answer.json()
    except requests.JSONDecodeError as error:
        message = f'Ошибка при распаковке запроса: {error}'
        raise RequestsError(message)
    return api_answer_json


def check_response(response):
    """Проверяет корректность входных данных."""
    if not isinstance(response, dict):
        message = 'Тип данных не соответствует должному'
        raise TypeError(message)
    if response.get('homeworks') is None:
        message = 'Отсутствие данных о работ в ответе'
        raise ApiAnsverError(message)
    if response.get('current_date') is None:
        message = 'Отсутствие данных о времени в ответе'
        raise ApiAnsverError(message)
    homeworks = response.get('homeworks')
    if homeworks is None:
        message = 'Отсутствие ожидаемых ключей в ответе API'
        raise TypeError(message)
    if not isinstance(homeworks, list):
        message = 'Тип данных не соответствует должному'
        raise TypeError(message)
    return response


def parse_status(homework):
    """Проверяет статус работы."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_name is None:
        message = 'В ответе API домашки нет ключа homework_name'
        raise StatusError(message)
    if homework_status not in HOMEWORK_VERDICTS:
        message = ('Неожиданный статус домашней работы,'
                   'обнаруженный в ответе API')
        raise StatusError(message)
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - ONE_DAY_IN_SECONDS
    last_message = None
    while True:
        try:
            request = get_api_answer(timestamp)
            response = check_response(request)
            new_homeworks = response.get('homeworks')
            if new_homeworks:
                send_message(bot,
                             parse_status(new_homeworks[0]))
            else:
                message = 'Пока нет никакой информации'
                logging.info(message, exc_info=True)
            timestamp = response.get('current_date', timestamp)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if message != last_message:
                logging.error(error.args[0], exc_info=True)
                send_message(bot, message)
                last_message = message
        else:
            last_message = None
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        filename='main.log',
        encoding='utf-8',
        format='%(asctime)s, %(levelname)s, %(message)s'
    )

    main()
