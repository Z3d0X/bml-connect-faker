"""Signed webhook delivery. Follows src/php/webhooks.php."""

import hashlib
import http.client
import json
import os
import secrets
import ssl
import time
from urllib.parse import urlsplit

from config import CONFIG
from bootstrap import query, now


def send_webhook(transaction, payload):
    """Sends the event to the transaction's own webhook, every registered webhook and the configured one."""
    registered = [row['hook_url'] for row in query('select hook_url from webhooks')]
    targets = [url for url in [transaction['webhook_url'], *registered, CONFIG['webhook_url']] if url]

    for url in dict.fromkeys(targets):
        deliver(url, json.dumps(payload, separators=(',', ':')))


def deliver(url, body):
    """BML signs the headers only: sha256(nonce + timestamp + apiKey). The body is not covered."""
    nonce = secrets.token_hex(16)
    sent_at = str(int(time.time()))
    status, response = None, ''

    try:
        target = urlsplit(url)

        if target.scheme == 'https':
            context = ssl.create_default_context()

            if os.path.isfile(CONFIG['ca_file']):
                context.load_verify_locations(CONFIG['ca_file'])

            connection = http.client.HTTPSConnection(target.hostname, target.port, timeout=10, context=context)
        elif target.scheme == 'http':
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=10)
        else:
            raise ValueError('Unsupported webhook URL')

        try:
            connection.request('POST', (target.path or '/') + ('?' + target.query if target.query else ''), body.encode(), {
                'Content-Type': 'application/json',
                'X-Originator': 'PomeloPay-Webhooks',
                'X-Signature-Nonce': nonce,
                'X-Signature-Timestamp': sent_at,
                'X-Signature': hashlib.sha256((nonce + sent_at + CONFIG['api_key']).encode()).hexdigest(),
            })
            answer = connection.getresponse()
            status, response = answer.status, answer.read().decode('utf-8', 'replace')
        finally:
            connection.close()
    except Exception as error:
        response = str(error)

    query('insert into deliveries (url, body, status, response, created) values (?, ?, ?, ?, ?)', [
        url, body, status, response[:2000], now(),
    ])
