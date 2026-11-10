"""Database and helpers. Follows src/php/bootstrap.php."""

import html
import json
import os
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timezone

from config import SHARED, CONFIG


# Test cards on the hosted page, by card number. shared/README.md explains the fields.
with open(os.path.join(SHARED, 'cards.json'), encoding='utf-8') as cards:
    TEST_CARDS = {card['number']: card for card in json.load(cards)}

PENDING_STATES = ('INITIATED', 'QR_CODE_GENERATED')

# The request being served on this thread: its database connection, body and base URL.
request = threading.local()


def connect():
    os.makedirs(os.path.dirname(CONFIG['database']), exist_ok=True)

    connection = sqlite3.connect(CONFIG['database'], isolation_level=None)
    connection.row_factory = lambda cursor, row: {column[0]: row[index] for index, column in enumerate(cursor.description)}

    with open(os.path.join(SHARED, 'schema.sql'), encoding='utf-8') as schema:
        connection.executescript(schema.read())

    return connection


def bindable(value):
    return json.dumps(value) if isinstance(value, (dict, list)) else value


def query(sql, bindings=()):
    return request.db.execute(sql, [bindable(value) for value in bindings]).fetchall()


def find(table, id):
    rows = query('select * from %s where id = ?' % table, [text(id)])

    return rows[0] if rows else None


def new_id():
    """Ids look like BML's: 24 hex characters."""
    return secrets.token_hex(12)


def timestamp(moment=None):
    moment = moment or datetime.now(timezone.utc)

    return moment.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (moment.microsecond // 1000)


def now():
    return timestamp()


def text(value):
    """A value bound for a text column: scalars become strings, as PDO does."""
    if value is None:
        return None

    if isinstance(value, str):
        return value

    return json.dumps(value)


class Reply(Exception):
    def __init__(self, status, headers=None, body=''):
        super().__init__(status)
        self.status = status
        self.headers = headers or {}
        self.body = body


def respond_json(data, status=200):
    return Reply(status, {'Content-Type': 'application/json'}, json.dumps(data, indent=4))


def respond_html(body, status=200):
    return Reply(status, {'Content-Type': 'text/html; charset=utf-8'}, body)


def redirect(url):
    return Reply(303, {'Location': url})


def fail(status, message):
    """Raises, so it can end a handler from anywhere."""
    raise respond_json({'message': message}, status)


def json_body():
    try:
        decoded = json.loads(request.body)
    except ValueError:
        return {}

    return decoded if isinstance(decoded, dict) else {}


def e(value):
    return '' if value is None else html.escape(str(value), quote=True)


def render(template, values):
    """Fills a template from shared/templates: {{name}} is escaped, {{{name}}} is inserted as it is."""
    with open(os.path.join(SHARED, 'templates', template + '.html'), encoding='utf-8') as source:
        return re.sub(
            r'\{\{(\{?)(\w+)\}?\}\}',
            lambda match: e(values.get(match[2])) if match[1] == '' else str(values.get(match[2], '')),
            source.read(),
        )


def padded_card_number(number):
    return number[:6] + '*' * (len(number) - 10) + number[-4:]
