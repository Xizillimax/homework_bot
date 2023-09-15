import logging
import os
import time

import requests
import telegram
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    filename='main.log',
    encoding='utf-8',
    format='%(asctime)s, %(levelname)s, %(message)s')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler('my_log.log', maxBytes=50000000, backupCount=5)
logger.addHandler(handler)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


class StatusError(Exception):
    """Ошибка статутса работы."""

    pass


class ApiAnsverError(Exception):
    """Ошибка Api ответа о данных работы."""

    pass


def check_tokens():
    """Проверяет токены на наличие."""
    if not all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)):
        message = (('отсутствие обязательных переменных'),
                   ('окружения во время запуска бота'))
        logging.critical(message, exc_info=True)
        return True
    return False


def send_message(bot, message):
    """Отправляет сообщения."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception:
        logging.error('сбой при отправке сообщения в Telegram', exc_info=True)
    else:
        logging.debug('удачная отправка любого сообщения в Telegram',
                      exc_info=True)


def get_api_answer(params):
    """Получает данные с сайта и проверяет их."""
    try:
        api_answer = requests.get(ENDPOINT, params=params, headers=HEADERS)
    except requests.RequestException as error:
        message = f'Ошибка при отправке запроса: {error}'
        logging.error(message, exc_info=True)
    api_answer_json = api_answer.json()
    if api_answer_json.get('homeworks') is None:
        message = 'Отсутствие данных о работ в ответе'
        logging.error(message, exc_info=True)
        raise ApiAnsverError(message)
    if api_answer_json.get('current_date') is None:
        message = 'Отсутствие данных о времени в ответе'
        logging.error(message, exc_info=True)
        raise ApiAnsverError(message)
    if api_answer_json.get('code') == 'UnknownError':
        message = 'Недоступность эндпоинта, ошибка 400'
        logging.error(message, exc_info=True)
        raise ApiAnsverError(message)
    if api_answer_json.get('code') == 'not_authenticated':
        message = api_answer_json.get('message')
        logging.error(message, exc_info=True)
        raise ApiAnsverError(message)
    if api_answer_json.get('error') is not None:
        message = 'Kюбые другие сбои при запросе к эндпоинту'
        logging.error(message, exc_info=True)
        raise ApiAnsverError(message)
    return api_answer_json


def check_response(response):
    """Проверяет корректность входных данных."""
    if not isinstance(response, dict):
        message = 'Тип данных не соответствует должному'
        logging.error(message, exc_info=True)
        raise TypeError(message)
    homework = response.get('homeworks')
    if homework is None:
        message = 'Отсутствие ожидаемых ключей в ответе API'
        logging.error(message, exc_info=True)
        raise TypeError(message)
    if not isinstance(homework, list):
        message = 'Тип данных не соответствует должному'
        logging.error(message, exc_info=True)
        raise TypeError(message)
    if len(homework) == 0:
        message = 'Нет работ за данный период'
        logging.info(message, exc_info=True)
        return 0
    homework_status = homework[0].get('status')
    if homework_status not in HOMEWORK_VERDICTS:
        message = (('Неожиданный статус домашней работы,'),
                   ('обнаруженный в ответе API'))
        logging.error(message, exc_info=True)
        raise TypeError(message)
    return response


def parse_status(homework):
    """Проверяет статус работы."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_name is None:
        message = 'В ответе API домашки нет ключа homework_name'
        logging.error(message, exc_info=True)
        raise StatusError(message)
    if homework_status not in HOMEWORK_VERDICTS:
        message = 'Статус домашки не найден в базе статусов'
        logging.error(message, exc_info=True)
        raise StatusError(message)
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if check_tokens():
        exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    params = {
        'from_date': int(time.time())
    }
    new_status_homework = None
    while True:
        try:
            new_homework = get_api_answer(params)
            response = check_response(new_homework)
            if response != 0:
                status_homework = response.get('homeworks')[0].get('status')
                if (new_status_homework != status_homework):
                    send_message(bot,
                                 parse_status(response.get('homeworks')[0]))
                else:
                    message = 'Изменений нет'
                    logging.info(message, exc_info=True)
                    send_message(bot, message)
            else:
                message = 'Пока нет никакой информации'
                logging.info(message, exc_info=True)
                send_message(bot, message)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
