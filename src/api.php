<?php

declare(strict_types=1);

function authenticate(): void
{
    if (($_SERVER['HTTP_AUTHORIZATION'] ?? '') !== config('api_key')) {
        fail(401, 'Unauthorized');
    }
}

function require_fields(array $input, array $fields): void
{
    $missing = array_values(array_filter($fields, fn (string $field): bool => ($input[$field] ?? '') === ''));

    if ($missing !== []) {
        fail(422, 'Missing required fields: '.implode(', ', $missing));
    }
}

function api_create_customer(): never
{
    $input = json_body();
    require_fields($input, ['name', 'email']);

    respond_json(customer_json(create_customer($input)), 201);
}

function api_create_transaction(): never
{
    $input = json_body();
    require_fields($input, ['amount', 'currency']);

    if (! is_int($input['amount']) || $input['amount'] <= 0) {
        fail(422, 'amount must be a positive integer in minor units');
    }

    $customerId = $input['customerId'] ?? null;

    if ($customerId !== null && find('customers', (string) $customerId) === null) {
        fail(404, 'Customer not found');
    }

    if ($customerId === null && is_array($input['customer'] ?? null)) {
        require_fields($input['customer'], ['name', 'email']);
        $customerId = create_customer($input['customer'])['id'];
    }

    $tokenization = $input['tokenizationDetails'] ?? [];
    $tokenize = ($tokenization['tokenize'] ?? false) === true;

    if ($tokenize && $customerId === null) {
        fail(422, 'Tokenization needs customerId or customer');
    }

    $id = new_id();
    $now = now();
    $lifetimeDays = (int) config('transaction_lifetime_days');

    query(
        'insert into transactions (id, short_code, amount, currency, state, customer_id, local_id, customer_reference, redirect_url, webhook_url, provider, tokenize, payment_type, recurring_frequency, expires, created, updated)
         values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [
            $id,
            substr(bin2hex(random_bytes(5)), 0, 10),
            $input['amount'],
            strtoupper((string) $input['currency']),
            'QR_CODE_GENERATED',
            $customerId,
            $input['localId'] ?? null,
            $input['customerReference'] ?? null,
            $input['redirectUrl'] ?? null,
            $input['webhook'] ?? null,
            $input['provider'] ?? null,
            (int) $tokenize,
            $tokenize ? ($tokenization['paymentType'] ?? 'UNSCHEDULED') : null,
            $tokenize ? ($tokenization['recurringFrequency'] ?? 'UNSCHEDULED') : null,
            gmdate('Y-m-d\TH:i:s.v\Z', time() + $lifetimeDays * 86400),
            $now,
            $now,
        ],
    );

    respond_json(transaction_json(find('transactions', $id)), 201);
}

function api_get_transaction(string $id): never
{
    respond_json(transaction_json(find('transactions', $id) ?? fail(404, 'Transaction not found')));
}

function api_cancel_transaction(string $id): never
{
    $transaction = find('transactions', $id) ?? fail(404, 'Transaction not found');

    if (! in_array($transaction['state'], PENDING_STATES, true)) {
        fail(400, "Transaction is {$transaction['state']} and cannot be cancelled");
    }

    respond_json(transaction_json(settle($transaction, 'CANCELLED')));
}

function api_list_tokens(string $customerId): never
{
    find('customers', $customerId) ?? fail(404, 'Customer not found');

    $tokens = query('select * from tokens where customer_id = ? and deleted = 0 order by created', [$customerId])->fetchAll();

    respond_json(array_map(token_json(...), $tokens));
}

function api_delete_token(string $customerId, string $tokenId): never
{
    $token = find('tokens', $tokenId);

    if ($token === null || $token['customer_id'] !== $customerId || $token['deleted']) {
        fail(404, 'Token not found');
    }

    query('update tokens set deleted = 1 where id = ?', [$tokenId]);

    http_response_code(204);
    exit;
}

function api_charge_token(): never
{
    $input = json_body();
    require_fields($input, ['customerId', 'transactionId', 'tokenId']);

    $transaction = find('transactions', (string) $input['transactionId']) ?? fail(404, 'Transaction not found');
    $token = find('tokens', (string) $input['tokenId']);

    if ($token === null || $token['deleted'] || $token['customer_id'] !== $input['customerId']) {
        fail(404, 'Token not found for this customer');
    }

    if ($transaction['customer_id'] !== null && $transaction['customer_id'] !== $input['customerId']) {
        fail(422, 'Transaction belongs to another customer');
    }

    if (! is_payable($transaction)) {
        fail(400, "Transaction is {$transaction['state']} and cannot be charged");
    }

    if ($transaction['customer_id'] === null) {
        query('update transactions set customer_id = ? where id = ?', [$input['customerId'], $transaction['id']]);
        $transaction = find('transactions', $transaction['id']);
    }

    respond_json(transaction_json(charge_saved_card($transaction, $token)));
}

function api_register_webhook(): never
{
    $input = json_body();
    require_fields($input, ['hookUrl']);

    $id = new_id();
    query('insert into webhooks (id, hook_url, created) values (?, ?, ?)', [$id, $input['hookUrl'], now()]);

    respond_json(['id' => $id, 'hookUrl' => $input['hookUrl']], 201);
}
