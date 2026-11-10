#!/usr/bin/env python3

"""
BML Connect Faker in Python. Needs Python 3.8+ and nothing else.

    python3 src/python/server.py

The files in this folder follow the PHP ones of the same name, function by function: this one is
src/php/server.php. A change to one implementation belongs in all of them; tests/conformance.py checks
that they agree. The schema, the test cards and the HTML are in shared/, read by every implementation.
"""

import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from config import CONFIG
from bootstrap import request, connect, Reply, respond_json, fail
from api import (
    authenticate, api_create_customer, api_create_transaction, api_get_transaction, api_cancel_transaction,
    api_list_tokens, api_delete_token, api_charge_token, api_register_webhook,
)
from pages import (
    page_pay, page_pay_submit, page_short_link, page_dashboard, dashboard_toggle_fail_next, dashboard_expire_card,
    dashboard_resend, dashboard_reset,
)


# (method, path pattern, handler, needs the API key)
ROUTES = [
    ('POST', r'/public-customers', api_create_customer, True),
    ('POST', r'/public-customers/charge', api_charge_token, True),
    ('GET', r'/public-customers/([^/]+)/tokens', api_list_tokens, True),
    ('DELETE', r'/public-customers/([^/]+)/tokens/([^/]+)', api_delete_token, True),
    ('POST', r'/public/v2/transactions', api_create_transaction, True),
    ('GET', r'/public/v2/transactions/([^/]+)', api_get_transaction, True),
    ('POST', r'/public/transactions/([^/]+)/cancel', api_cancel_transaction, True),
    ('POST', r'/public/webhooks', api_register_webhook, True),

    ('GET', r'/pay/([^/]+)', page_pay, False),
    ('POST', r'/pay/([^/]+)', page_pay_submit, False),
    ('GET', r'/p/([^/]+)', page_short_link, False),

    ('GET', r'/', page_dashboard, False),
    ('POST', r'/dashboard/tokens/([^/]+)/fail-next', dashboard_toggle_fail_next, False),
    ('POST', r'/dashboard/tokens/([^/]+)/expire', dashboard_expire_card, False),
    ('POST', r'/dashboard/deliveries/([0-9]+)/resend', dashboard_resend, False),
    ('POST', r'/dashboard/reset', dashboard_reset, False),
]


def handle(method, path):
    for route_method, pattern, handler, needs_api_key in ROUTES:
        matches = re.fullmatch(pattern, path) if route_method == method else None

        if matches is not None:
            if needs_api_key:
                authenticate()

            return handler(*matches.groups())

    fail(404, 'No route for %s %s' % (method, path))


class Handler(BaseHTTPRequestHandler):
    def serve(self):
        path = self.path.split('?')[0].rstrip('/') or '/'
        scheme = 'https' if self.headers.get('X-Forwarded-Proto') == 'https' else 'http'

        request.headers = self.headers
        request.body = self.rfile.read(int(self.headers.get('Content-Length') or 0)).decode('utf-8', 'replace')
        request.base_url = scheme + '://' + self.headers.get('Host', 'localhost')
        request.db = connect()

        try:
            reply = handle(self.command, path)
        except Reply as thrown:
            reply = thrown
        except Exception as error:
            self.log_error('%r', error)
            reply = respond_json({'message': 'Faker error: %s' % error}, 500)
        finally:
            request.db.close()

        body = reply.body.encode('utf-8')
        self.send_response(reply.status)

        for name, value in reply.headers.items():
            self.send_header(name, value)

        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = serve


if __name__ == '__main__':
    server = ThreadingHTTPServer((CONFIG['host'], CONFIG['port']), Handler)
    print('BML Connect Faker (Python) listening on http://%s:%d' % (CONFIG['host'], CONFIG['port']), flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
