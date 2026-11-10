"""Transactions, saved cards, charging. Follows src/php/payments.php."""

import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

from config import CONFIG
from bootstrap import TEST_CARDS, PENDING_STATES, request, query, find, new_id, now, text, padded_card_number
from webhooks import send_webhook


def create_customer(input):
    id = new_id()
    query('insert into customers (id, name, email, payload, created) values (?, ?, ?, ?, ?)', [
        id, text(input['name']), text(input['email']), json.dumps(input), now(),
    ])

    return find('customers', id)


def customer_json(customer):
    return {
        **json.loads(customer['payload']),
        'id': customer['id'],
        'name': customer['name'],
        'email': customer['email'],
        'created': customer['created'],
    }


def transaction_json(transaction):
    return {
        'id': transaction['id'],
        'amount': int(transaction['amount']),
        'currency': transaction['currency'],
        'state': transaction['state'],
        'customerId': transaction['customer_id'],
        'localId': transaction['local_id'],
        'customerReference': transaction['customer_reference'],
        'redirectUrl': transaction['redirect_url'],
        'webhook': transaction['webhook_url'],
        'provider': transaction['provider'],
        'url': request.base_url + '/pay/' + transaction['id'],
        'shortUrl': request.base_url + '/p/' + transaction['short_code'],
        'tokenizationDetails': {
            'tokenize': True,
            'paymentType': transaction['payment_type'],
            'recurringFrequency': transaction['recurring_frequency'],
        } if transaction['tokenize'] else None,
        'paddedCardNumber': transaction['padded_card_number'],
        'cardExpMonth': None if transaction['card_exp_month'] is None else int(transaction['card_exp_month']),
        'cardExpYear': None if transaction['card_exp_year'] is None else int(transaction['card_exp_year']),
        'nextAction': None,
        'expires': transaction['expires'],
        'created': transaction['created'],
        'updated': transaction['updated'],
    }


def token_json(token):
    return {
        'id': token['id'],
        'customerId': token['customer_id'],
        'brand': token['brand'],
        'paddedCardNumber': token['padded_card_number'],
        'tokenExpiryMonth': int(token['exp_month']),
        'tokenExpiryYear': int(token['exp_year']),
        'tokenAgreementType': token['agreement_type'],
        'deleted': bool(token['deleted']),
        'created': token['created'],
    }


def is_payable(transaction):
    return transaction['state'] in PENDING_STATES and transaction['expires'] > now()


def settle(transaction, state, card=None, token=None):
    """Moves a pending transaction to its final state and tells the merchant, as BML does."""
    card = card or {}
    query(
        'update transactions set state = ?, token_id = ?, padded_card_number = ?, card_exp_month = ?, card_exp_year = ?, updated = ? where id = ?',
        [
            state,
            token['id'] if token else None,
            card.get('padded_card_number'),
            card.get('exp_month'),
            card.get('exp_year'),
            now(),
            transaction['id'],
        ],
    )

    settled = find('transactions', transaction['id'])

    send_webhook(settled, {
        'eventType': 'NOTIFY_TRANSACTION_CHANGE',
        'transactionId': settled['id'],
        'state': settled['state'],
        'amount': int(settled['amount']),
        'currency': settled['currency'],
    })

    return settled


def pay_on_hosted_page(transaction, card_number):
    """Paying on the hosted page. A card is saved only when the payment goes through."""
    outcome = 'FAILED' if TEST_CARDS[card_number]['first'] == 'decline' else 'CONFIRMED'
    today = datetime.now(timezone.utc)
    card = {
        'padded_card_number': padded_card_number(card_number),
        'exp_month': today.month,
        'exp_year': today.year + (-1 if TEST_CARDS[card_number].get('expired') else 3),
    }
    saves = bool(transaction['tokenize']) and transaction['customer_id'] is not None

    token = save_card(transaction, card_number, card) if outcome == 'CONFIRMED' and saves else None

    settled = settle(transaction, outcome, card, token)

    if saves:
        send_webhook(settled, {
            'eventType': 'NOTIFY_TOKENISATION_STATUS',
            'customerId': settled['customer_id'],
            'transactionId': settled['id'],
            'tokenisationStatus': 'FAILED' if token is None else 'SUCCESS',
        })

    return settled


def save_card(transaction, card_number, card):
    id = new_id()
    query(
        'insert into tokens (id, customer_id, card_number, brand, padded_card_number, exp_month, exp_year, agreement_type, created) values (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [
            id,
            transaction['customer_id'],
            card_number,
            TEST_CARDS[card_number]['brand'],
            card['padded_card_number'],
            card['exp_month'],
            card['exp_year'],
            transaction['payment_type'] or 'UNSCHEDULED',
            now(),
        ],
    )

    return find('tokens', id)


def charge_saved_card(transaction, token):
    """A charge on a saved card settles at once: no 3DS, no hosted page."""
    expired = '%04d-%02d' % (token['exp_year'], token['exp_month']) < now()[:7]
    declines = expired or bool(token['fail_next_charge']) or TEST_CARDS.get(token['card_number'], {}).get('later') == 'decline'

    if token['fail_next_charge']:
        query('update tokens set fail_next_charge = 0 where id = ?', [token['id']])

    return settle(transaction, 'FAILED' if declines else 'CONFIRMED', {
        'padded_card_number': token['padded_card_number'],
        'exp_month': token['exp_month'],
        'exp_year': token['exp_year'],
    }, token)


def redirect_back_url(transaction):
    """
    The query string BML appends to `redirectUrl`. Merchants must not trust it; they read the transaction.
    The signature here follows the v1 PHP SDK's request signature, as BML documents none for the redirect.
    """
    signature = hashlib.sha1(
        ('amount=%s&currency=%s&apiKey=%s' % (transaction['amount'], transaction['currency'], CONFIG['api_key'])).encode()
    ).hexdigest()
    separator = '&' if '?' in transaction['redirect_url'] else '?'

    return transaction['redirect_url'] + separator + urlencode({
        'transactionId': transaction['id'],
        'state': transaction['state'],
        'signature': signature,
    })
