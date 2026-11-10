#!/usr/bin/env python3

"""
Runs the same black-box checks against every implementation of the faker, so they stay in step.

    python3 tests/conformance.py              # every implementation whose runtime is installed
    python3 tests/conformance.py node python  # only these

Each implementation is started on a free port with a throwaway database. Needs Python 3.8+ only.
"""

import hashlib
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_KEY = 'conformance-key'

IMPLEMENTATIONS = {
    'php': lambda port: ['php', '-S', '127.0.0.1:%d' % port, 'src/php/server.php'],
    'node': lambda port: ['node', 'src/node/server.mjs'],
    'python': lambda port: [sys.executable, 'src/python/server.py'],
}

TRANSACTION_KEYS = [
    'id', 'amount', 'currency', 'state', 'customerId', 'localId', 'customerReference', 'redirectUrl', 'webhook',
    'provider', 'url', 'shortUrl', 'tokenizationDetails', 'paddedCardNumber', 'cardExpMonth', 'cardExpYear',
    'nextAction', 'expires', 'created', 'updated',
]

TOKEN_KEYS = [
    'id', 'customerId', 'brand', 'paddedCardNumber', 'tokenExpiryMonth', 'tokenExpiryYear', 'tokenAgreementType',
    'deleted', 'created',
]


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))

        return listener.getsockname()[1]


class Merchant:
    """Stands in for the developer's app: it receives the webhooks."""

    def __init__(self):
        received = self.received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
                received.append((self.headers, json.loads(body)))
                self.send_response(200)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'ok')

            def log_message(self, *arguments):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = 'http://127.0.0.1:%d/webhooks/bml' % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def take(self):
        events = list(self.received)
        del self.received[:]

        return events


class Faker:
    def __init__(self, port):
        self.port = port

    def call(self, method, path, body=None, form=None, key=API_KEY):
        headers = {}
        payload = None

        if key is not None:
            headers['Authorization'] = key

        if body is not None:
            payload = json.dumps(body)
            headers['Content-Type'] = 'application/json'

        if form is not None:
            payload = urlencode(form)
            headers['Content-Type'] = 'application/x-www-form-urlencoded'

        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        connection.request(method, path, payload, headers)
        response = connection.getresponse()
        raw = response.read().decode()
        connection.close()

        is_json = (response.getheader('Content-Type') or '').startswith('application/json')

        return response.status, (json.loads(raw) if is_json and raw else raw), response.getheader('Location')


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def equal(actual, expected, what):
    check(actual == expected, '%s: expected %r, got %r' % (what, expected, actual))


def run_checks(faker, merchant):
    base = 'http://127.0.0.1:%d' % faker.port

    # Authentication, routing, validation.
    status, body, _ = faker.call('POST', '/public-customers', {'name': 'A', 'email': 'a@example.test'}, key='wrong')
    equal((status, body), (401, {'message': 'Unauthorized'}), 'wrong API key')

    status, body, _ = faker.call('GET', '/nowhere')
    equal((status, body), (404, {'message': 'No route for GET /nowhere'}), 'unknown route')

    status, body, _ = faker.call('POST', '/public-customers', {'name': 'A'})
    equal((status, body), (422, {'message': 'Missing required fields: email'}), 'customer without email')

    status, body, _ = faker.call('POST', '/public/v2/transactions', {'amount': 0, 'currency': 'MVR'})
    equal(status, 422, 'zero amount')

    status, body, _ = faker.call('POST', '/public/v2/transactions', {'amount': '100', 'currency': 'MVR'})
    equal(status, 422, 'string amount')

    status, body, _ = faker.call('POST', '/public/v2/transactions', {'amount': 100, 'currency': 'MVR', 'customerId': 'nobody'})
    equal((status, body), (404, {'message': 'Customer not found'}), 'unknown customer')

    status, body, _ = faker.call('POST', '/public/v2/transactions', {'amount': 100, 'currency': 'MVR', 'tokenizationDetails': {'tokenize': True}})
    equal(status, 422, 'tokenize without a customer')

    # A customer keeps the extra fields it was created with.
    status, customer, _ = faker.call('POST', '/public-customers', {'name': 'Aisha', 'email': 'aisha@example.test', 'phone': '7771234'})
    equal(status, 201, 'create customer')
    equal(list(customer), ['name', 'email', 'phone', 'id', 'created'], 'customer fields')
    check(len(customer['id']) == 24, 'customer id is 24 hex characters')

    # A transaction that saves the card, paid on the hosted page with the 3DS card.
    status, transaction, _ = faker.call('POST', '/public/v2/transactions', {
        'amount': 123456,
        'currency': 'mvr',
        'customerId': customer['id'],
        'localId': 'order-1',
        'redirectUrl': 'http://merchant.test/return?order=1',
        'webhook': merchant.url,
        'tokenizationDetails': {'tokenize': True, 'paymentType': 'RECURRING'},
    })
    equal(status, 201, 'create transaction')
    equal(list(transaction), TRANSACTION_KEYS, 'transaction fields')
    equal(transaction['state'], 'QR_CODE_GENERATED', 'new transaction state')
    equal(transaction['currency'], 'MVR', 'currency is upper-cased')
    equal(transaction['url'], '%s/pay/%s' % (base, transaction['id']), 'payment page url')
    equal(transaction['tokenizationDetails'], {'tokenize': True, 'paymentType': 'RECURRING', 'recurringFrequency': 'UNSCHEDULED'}, 'tokenization details')
    check(len(transaction['expires']) == 24 and transaction['expires'].endswith('Z'), 'expires is an ISO timestamp with milliseconds')
    equal(merchant.take(), [], 'no webhook before payment')

    pay_path = '/pay/' + transaction['id']

    status, page, _ = faker.call('GET', pay_path, key=None)
    equal(status, 200, 'payment page')
    check('4111 1111 1111 1111' in page and 'MVR 1,234.56' in page and 'RECURRING' in page, 'payment page shows cards, amount and saving notice')

    status, _, location = faker.call('GET', '/p/' + urlsplit(transaction['shortUrl']).path.split('/')[-1], key=None)
    equal((status, location), (303, pay_path), 'short link')

    status, _, location = faker.call('POST', pay_path, form={'action': 'pay', 'card': '1234'}, key=None)
    equal((status, location), (303, pay_path), 'unknown card goes back to the page')

    status, page, _ = faker.call('POST', pay_path, form={'action': 'pay', 'card': '4000000000003220'}, key=None)
    check(status == 200 and '3D Secure check' in page, '3DS card asks for 3D Secure')
    equal(merchant.take(), [], 'no webhook before 3DS approval')

    status, _, location = faker.call('POST', pay_path, form={'action': '3ds-approve', 'card': '4000000000003220'}, key=None)
    equal(status, 303, 'paying redirects to the merchant')
    check(location.startswith('http://merchant.test/return?order=1&transactionId='), 'redirect keeps the merchant query string')
    returned = parse_qs(urlsplit(location).query)
    equal(returned['transactionId'], [transaction['id']], 'redirect transactionId')
    equal(returned['state'], ['CONFIRMED'], 'redirect state')
    equal(returned['signature'], [hashlib.sha1(('amount=123456&currency=MVR&apiKey=' + API_KEY).encode()).hexdigest()], 'redirect signature')

    events = merchant.take()
    equal([event for _, event in events], [
        {'eventType': 'NOTIFY_TRANSACTION_CHANGE', 'transactionId': transaction['id'], 'state': 'CONFIRMED', 'amount': 123456, 'currency': 'MVR'},
        {'eventType': 'NOTIFY_TOKENISATION_STATUS', 'customerId': customer['id'], 'transactionId': transaction['id'], 'tokenisationStatus': 'SUCCESS'},
    ], 'webhooks after payment')

    for headers, _ in events:
        equal(headers['X-Originator'], 'PomeloPay-Webhooks', 'webhook originator')
        check(headers['X-Signature-Timestamp'].isdigit() and abs(int(headers['X-Signature-Timestamp']) - time.time()) < 60, 'webhook timestamp is Unix seconds')
        signature = hashlib.sha256((headers['X-Signature-Nonce'] + headers['X-Signature-Timestamp'] + API_KEY).encode()).hexdigest()
        equal(headers['X-Signature'], signature, 'webhook signature')

    status, paid, _ = faker.call('GET', '/public/v2/transactions/' + transaction['id'])
    equal((status, paid['state'], paid['paddedCardNumber']), (200, 'CONFIRMED', '400000******3220'), 'paid transaction')
    equal(paid['cardExpMonth'], time.gmtime().tm_mon, 'card expiry month')

    status, page, _ = faker.call('GET', pay_path, key=None)
    check(status == 200 and 'CONFIRMED' in page, 'payment page of a paid transaction shows the result')

    status, tokens, _ = faker.call('GET', '/public-customers/%s/tokens' % customer['id'])
    equal((status, len(tokens)), (200, 1), 'token list')
    token = tokens[0]
    equal(list(token), TOKEN_KEYS, 'token fields')
    equal((token['brand'], token['paddedCardNumber'], token['tokenAgreementType'], token['deleted']), ('VISA', '400000******3220', 'RECURRING', False), 'token')

    # Charging the saved card.
    def charge(expected_status=200):
        _, pending, _ = faker.call('POST', '/public/v2/transactions', {'amount': 5000, 'currency': 'MVR', 'webhook': merchant.url})
        status, charged, _ = faker.call('POST', '/public-customers/charge', {'customerId': customer['id'], 'transactionId': pending['id'], 'tokenId': token['id']})
        equal(status, expected_status, 'charge status')

        return charged

    charged = charge()
    equal((charged['state'], charged['customerId'], charged['paddedCardNumber']), ('CONFIRMED', customer['id'], '400000******3220'), 'charge on a saved card')
    equal([event['state'] for _, event in merchant.take()], ['CONFIRMED'], 'one webhook per charge')

    status, body, _ = faker.call('POST', '/public-customers/charge', {'customerId': customer['id'], 'transactionId': charged['id'], 'tokenId': token['id']})
    equal((status, body), (400, {'message': 'Transaction is CONFIRMED and cannot be charged'}), 'charging a settled transaction')

    status, _, location = faker.call('POST', '/dashboard/tokens/%s/fail-next' % token['id'], key=None)
    equal((status, location), (303, '/'), 'fail-next switch')
    equal(charge()['state'], 'FAILED', 'charge after fail-next')
    equal(charge()['state'], 'CONFIRMED', 'fail-next applies once')

    faker.call('POST', '/dashboard/tokens/%s/expire' % token['id'], key=None)
    equal(charge()['state'], 'FAILED', 'charge on an expired card')
    merchant.take()

    # Cancelling.
    _, pending, _ = faker.call('POST', '/public/v2/transactions', {'amount': 700, 'currency': 'USD'})
    equal(pending['tokenizationDetails'], None, 'plain transaction has no tokenization details')
    status, cancelled, _ = faker.call('POST', '/public/transactions/%s/cancel' % pending['id'])
    equal((status, cancelled['state']), (200, 'CANCELLED'), 'cancel')
    status, body, _ = faker.call('POST', '/public/transactions/%s/cancel' % pending['id'])
    equal((status, body), (400, {'message': 'Transaction is CANCELLED and cannot be cancelled'}), 'cancel twice')

    # A declined card saves nothing; with no redirectUrl the page shows the result. The customer is created inline.
    _, declined, _ = faker.call('POST', '/public/v2/transactions', {
        'amount': 900, 'currency': 'MVR', 'webhook': merchant.url,
        'customer': {'name': 'Bilal', 'email': 'bilal@example.test'},
        'tokenizationDetails': {'tokenize': True},
    })
    status, page, _ = faker.call('POST', '/pay/' + declined['id'], form={'action': 'pay', 'card': '4000000000000002'}, key=None)
    check(status == 200 and 'FAILED' in page, 'declined card shows the result')
    equal([(event['eventType'], event.get('state'), event.get('tokenisationStatus')) for _, event in merchant.take()], [
        ('NOTIFY_TRANSACTION_CHANGE', 'FAILED', None),
        ('NOTIFY_TOKENISATION_STATUS', None, 'FAILED'),
    ], 'webhooks after a declined card')
    equal(faker.call('GET', '/public-customers/%s/tokens' % declined['customerId'])[1], [], 'declined card saves nothing')

    # A registered webhook gets every event; the dashboard lists and resends deliveries.
    status, hook, _ = faker.call('POST', '/public/webhooks', {'hookUrl': merchant.url + '?registered'})
    equal((status, list(hook), hook['hookUrl']), (201, ['id', 'hookUrl'], merchant.url + '?registered'), 'register webhook')
    _, pending, _ = faker.call('POST', '/public/v2/transactions', {'amount': 100, 'currency': 'MVR'})
    faker.call('POST', '/pay/' + pending['id'], form={'action': 'cancel'}, key=None)
    equal([event['state'] for _, event in merchant.take()], ['CANCELLED'], 'registered webhook receives events')

    status, page, _ = faker.call('GET', '/', key=None)
    check(status == 200 and transaction['id'] in page and token['id'] in page and 'order-1' in page, 'dashboard lists transactions and saved cards')

    status, _, location = faker.call('POST', '/dashboard/deliveries/1/resend', key=None)
    equal((status, location), (303, '/'), 'resend')
    equal(len(merchant.take()), 1, 'resend delivers again')

    # Deleting the saved card.
    token_path = '/public-customers/%s/tokens/%s' % (customer['id'], token['id'])
    equal(faker.call('DELETE', token_path)[:2], (204, ''), 'delete token')
    equal(faker.call('DELETE', token_path)[0], 404, 'delete token twice')
    equal(faker.call('GET', '/public-customers/%s/tokens' % customer['id'])[1], [], 'token list after delete')
    equal(charge(404), {'message': 'Token not found for this customer'}, 'charge on a deleted token')

    # Reset.
    equal(faker.call('POST', '/dashboard/reset', key=None)[0], 303, 'reset')
    equal(faker.call('GET', '/public/v2/transactions/' + transaction['id'])[0], 404, 'transaction is gone after reset')


def run(name, merchant):
    port = free_port()
    directory = tempfile.mkdtemp(prefix='bml-faker-')
    environment = dict(
        os.environ,
        BML_FAKER_API_KEY=API_KEY,
        BML_FAKER_DATABASE=os.path.join(directory, 'faker.sqlite'),
        BML_FAKER_HOST='127.0.0.1',
        BML_FAKER_PORT=str(port),
    )
    environment.pop('BML_FAKER_WEBHOOK_URL', None)
    log = open(os.path.join(directory, 'server.log'), 'w+')
    process = subprocess.Popen(IMPLEMENTATIONS[name](port), cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)

    try:
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

        merchant.take()
        run_checks(Faker(port), merchant)

        return None
    except Exception as error:
        log.seek(0)

        return '%s: %s\n%s' % (type(error).__name__, error, log.read()[-2000:])
    finally:
        process.terminate()
        process.wait()
        log.close()
        shutil.rmtree(directory, ignore_errors=True)


def main():
    names = sys.argv[1:] or list(IMPLEMENTATIONS)
    merchant = Merchant()
    failed = False

    for name in names:
        if name not in IMPLEMENTATIONS:
            sys.exit('Unknown implementation %r. Choose from: %s' % (name, ', '.join(IMPLEMENTATIONS)))

        if shutil.which(IMPLEMENTATIONS[name](0)[0]) is None:
            print('%-7s skipped, runtime not installed' % name)
            continue

        error = run(name, merchant)
        failed = failed or error is not None
        print('%-7s %s' % (name, 'ok' if error is None else 'FAILED\n' + error))

    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
