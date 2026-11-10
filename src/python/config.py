"""Defaults, each overridable by an environment variable. Follows src/php/config.php."""

import os


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHARED = os.path.join(ROOT, 'shared')


def env(name):
    return os.environ.get(name) or None


CONFIG = {
    'api_key': env('BML_FAKER_API_KEY') or 'test-api-key',
    'webhook_url': env('BML_FAKER_WEBHOOK_URL'),
    'database': env('BML_FAKER_DATABASE') or os.path.join(ROOT, 'storage', 'bml-connect-faker.sqlite'),
    'ca_file': env('BML_FAKER_CA_FILE') or os.path.expanduser('~/Library/Application Support/Herd/config/valet/CA/LaravelValetCASelfSigned.pem'),
    'transaction_lifetime_days': int(env('BML_FAKER_TRANSACTION_LIFETIME_DAYS') or 7),
    'host': env('BML_FAKER_HOST') or '127.0.0.1',
    'port': int(env('BML_FAKER_PORT') or 8787),
}
