// The BML Connect endpoints. Follows src/php/api.php.

import { randomBytes } from 'node:crypto';

import { config } from './config.mjs';
import {
    PENDING_STATES, query, find, newId, timestamp, now, text, Reply, respondJson, fail, jsonBody,
} from './bootstrap.mjs';
import {
    createCustomer, customerJson, transactionJson, tokenJson, isPayable, settle, chargeSavedCard,
} from './payments.mjs';

export function authenticate(request) {
    if ((request.headers.authorization ?? '') !== config.apiKey) {
        fail(401, 'Unauthorized');
    }
}

function requireFields(input, fields) {
    const missing = fields.filter((field) => (input[field] ?? '') === '');

    if (missing.length > 0) {
        fail(422, `Missing required fields: ${missing.join(', ')}`);
    }
}

export function apiCreateCustomer(request) {
    const input = jsonBody(request);
    requireFields(input, ['name', 'email']);

    return respondJson(customerJson(createCustomer(input)), 201);
}

export function apiCreateTransaction(request) {
    const input = jsonBody(request);
    requireFields(input, ['amount', 'currency']);

    if (! Number.isInteger(input.amount) || input.amount <= 0) {
        fail(422, 'amount must be a positive integer in minor units');
    }

    let customerId = input.customerId ?? null;

    if (customerId !== null && find('customers', customerId) === null) {
        fail(404, 'Customer not found');
    }

    if (customerId === null && typeof input.customer === 'object' && input.customer !== null) {
        requireFields(input.customer, ['name', 'email']);
        customerId = createCustomer(input.customer).id;
    }

    const tokenization = typeof input.tokenizationDetails === 'object' && input.tokenizationDetails !== null ? input.tokenizationDetails : {};
    const tokenize = tokenization.tokenize === true;

    if (tokenize && customerId === null) {
        fail(422, 'Tokenization needs customerId or customer');
    }

    const id = newId();
    const created = now();

    query(
        `insert into transactions (id, short_code, amount, currency, state, customer_id, local_id, customer_reference, redirect_url, webhook_url, provider, tokenize, payment_type, recurring_frequency, expires, created, updated)
         values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
            id,
            randomBytes(5).toString('hex'),
            input.amount,
            String(input.currency).toUpperCase(),
            'QR_CODE_GENERATED',
            text(customerId),
            text(input.localId),
            text(input.customerReference),
            text(input.redirectUrl),
            text(input.webhook),
            text(input.provider),
            tokenize,
            tokenize ? text(tokenization.paymentType ?? 'UNSCHEDULED') : null,
            tokenize ? text(tokenization.recurringFrequency ?? 'UNSCHEDULED') : null,
            timestamp(new Date(Date.now() + config.transactionLifetimeDays * 86_400_000)),
            created,
            created,
        ],
    );

    return respondJson(transactionJson(request, find('transactions', id)), 201);
}

export function apiGetTransaction(request, id) {
    return respondJson(transactionJson(request, find('transactions', id) ?? fail(404, 'Transaction not found')));
}

export async function apiCancelTransaction(request, id) {
    const transaction = find('transactions', id) ?? fail(404, 'Transaction not found');

    if (! PENDING_STATES.includes(transaction.state)) {
        fail(400, `Transaction is ${transaction.state} and cannot be cancelled`);
    }

    return respondJson(transactionJson(request, await settle(transaction, 'CANCELLED')));
}

export function apiListTokens(request, customerId) {
    find('customers', customerId) ?? fail(404, 'Customer not found');

    const tokens = query('select * from tokens where customer_id = ? and deleted = 0 order by created', [customerId]);

    return respondJson(tokens.map(tokenJson));
}

export function apiDeleteToken(request, customerId, tokenId) {
    const token = find('tokens', tokenId);

    if (token === null || token.customer_id !== customerId || token.deleted) {
        fail(404, 'Token not found');
    }

    query('update tokens set deleted = 1 where id = ?', [tokenId]);

    return new Reply(204);
}

export async function apiChargeToken(request) {
    const input = jsonBody(request);
    requireFields(input, ['customerId', 'transactionId', 'tokenId']);

    let transaction = find('transactions', input.transactionId) ?? fail(404, 'Transaction not found');
    const token = find('tokens', input.tokenId);

    if (token === null || token.deleted || token.customer_id !== input.customerId) {
        fail(404, 'Token not found for this customer');
    }

    if (transaction.customer_id !== null && transaction.customer_id !== input.customerId) {
        fail(422, 'Transaction belongs to another customer');
    }

    if (! isPayable(transaction)) {
        fail(400, `Transaction is ${transaction.state} and cannot be charged`);
    }

    if (transaction.customer_id === null) {
        query('update transactions set customer_id = ? where id = ?', [input.customerId, transaction.id]);
        transaction = find('transactions', transaction.id);
    }

    return respondJson(transactionJson(request, await chargeSavedCard(transaction, token)));
}

export function apiRegisterWebhook(request) {
    const input = jsonBody(request);
    requireFields(input, ['hookUrl']);

    const id = newId();
    query('insert into webhooks (id, hook_url, created) values (?, ?, ?)', [id, text(input.hookUrl), now()]);

    return respondJson({ id, hookUrl: input.hookUrl }, 201);
}
