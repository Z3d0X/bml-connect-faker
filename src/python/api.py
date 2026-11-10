"""The BML Connect endpoints. Follows src/php/api.php."""

import secrets
from datetime import datetime, timedelta, timezone

from config import CONFIG
from bootstrap import (
    PENDING_STATES, request, query, find, new_id, timestamp, now, text, Reply, respond_json, fail, json_body,
)
from payments import create_customer, customer_json, transaction_json, token_json, is_payable, settle, charge_saved_card


def authenticate():
    if request.headers.get('Authorization', '') != CONFIG['api_key']:
        fail(401, 'Unauthorized')


def require_fields(input, fields):
    values = input if isinstance(input, dict) else {}
    missing = [field for field in fields if values.get(field) in (None, '')]

    if missing:
        fail(422, 'Missing required fields: ' + ', '.join(missing))


def api_create_customer():
    input = json_body()
    require_fields(input, ['name', 'email'])

    return respond_json(customer_json(create_customer(input)), 201)


def api_create_transaction():
    input = json_body()
    require_fields(input, ['amount', 'currency'])

    if not isinstance(input['amount'], int) or isinstance(input['amount'], bool) or input['amount'] <= 0:
        fail(422, 'amount must be a positive integer in minor units')

    customer_id = input.get('customerId')

    if customer_id is not None and find('customers', customer_id) is None:
        fail(404, 'Customer not found')

    if customer_id is None and isinstance(input.get('customer'), (dict, list)):
        require_fields(input['customer'], ['name', 'email'])
        customer_id = create_customer(input['customer'])['id']

    tokenization = input.get('tokenizationDetails')
    tokenization = tokenization if isinstance(tokenization, dict) else {}
    tokenize = tokenization.get('tokenize') is True

    if tokenize and customer_id is None:
        fail(422, 'Tokenization needs customerId or customer')

    id = new_id()
    created = now()
    expires = datetime.now(timezone.utc) + timedelta(days=CONFIG['transaction_lifetime_days'])

    query(
        '''insert into transactions (id, short_code, amount, currency, state, customer_id, local_id, customer_reference, redirect_url, webhook_url, provider, tokenize, payment_type, recurring_frequency, expires, created, updated)
           values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        [
            id,
            secrets.token_hex(5),
            input['amount'],
            str(input['currency']).upper(),
            'QR_CODE_GENERATED',
            text(customer_id),
            text(input.get('localId')),
            text(input.get('customerReference')),
            text(input.get('redirectUrl')),
            text(input.get('webhook')),
            text(input.get('provider')),
            int(tokenize),
            text(tokenization.get('paymentType') or 'UNSCHEDULED') if tokenize else None,
            text(tokenization.get('recurringFrequency') or 'UNSCHEDULED') if tokenize else None,
            timestamp(expires),
            created,
            created,
        ],
    )

    return respond_json(transaction_json(find('transactions', id)), 201)


def api_get_transaction(id):
    return respond_json(transaction_json(find('transactions', id) or fail(404, 'Transaction not found')))


def api_cancel_transaction(id):
    transaction = find('transactions', id) or fail(404, 'Transaction not found')

    if transaction['state'] not in PENDING_STATES:
        fail(400, 'Transaction is %s and cannot be cancelled' % transaction['state'])

    return respond_json(transaction_json(settle(transaction, 'CANCELLED')))


def api_list_tokens(customer_id):
    find('customers', customer_id) or fail(404, 'Customer not found')

    tokens = query('select * from tokens where customer_id = ? and deleted = 0 order by created', [customer_id])

    return respond_json([token_json(token) for token in tokens])


def api_delete_token(customer_id, token_id):
    token = find('tokens', token_id)

    if token is None or token['customer_id'] != customer_id or token['deleted']:
        fail(404, 'Token not found')

    query('update tokens set deleted = 1 where id = ?', [token_id])

    return Reply(204)


def api_charge_token():
    input = json_body()
    require_fields(input, ['customerId', 'transactionId', 'tokenId'])

    transaction = find('transactions', input['transactionId']) or fail(404, 'Transaction not found')
    token = find('tokens', input['tokenId'])

    if token is None or token['deleted'] or token['customer_id'] != input['customerId']:
        fail(404, 'Token not found for this customer')

    if transaction['customer_id'] is not None and transaction['customer_id'] != input['customerId']:
        fail(422, 'Transaction belongs to another customer')

    if not is_payable(transaction):
        fail(400, 'Transaction is %s and cannot be charged' % transaction['state'])

    if transaction['customer_id'] is None:
        query('update transactions set customer_id = ? where id = ?', [input['customerId'], transaction['id']])
        transaction = find('transactions', transaction['id'])

    return respond_json(transaction_json(charge_saved_card(transaction, token)))


def api_register_webhook():
    input = json_body()
    require_fields(input, ['hookUrl'])

    id = new_id()
    query('insert into webhooks (id, hook_url, created) values (?, ?, ?)', [id, text(input['hookUrl']), now()])

    return respond_json({'id': id, 'hookUrl': input['hookUrl']}, 201)
