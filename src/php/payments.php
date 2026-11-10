<?php

declare(strict_types=1);

function create_customer(array $input): array
{
    $id = new_id();
    query('insert into customers (id, name, email, payload, created) values (?, ?, ?, ?, ?)', [
        $id, (string) $input['name'], (string) $input['email'], json_encode($input), now(),
    ]);

    return find('customers', $id);
}

function customer_json(array $customer): array
{
    return [
        ...json_decode($customer['payload'], true),
        'id' => $customer['id'],
        'name' => $customer['name'],
        'email' => $customer['email'],
        'created' => $customer['created'],
    ];
}

function transaction_json(array $transaction): array
{
    return [
        'id' => $transaction['id'],
        'amount' => (int) $transaction['amount'],
        'currency' => $transaction['currency'],
        'state' => $transaction['state'],
        'customerId' => $transaction['customer_id'],
        'localId' => $transaction['local_id'],
        'customerReference' => $transaction['customer_reference'],
        'redirectUrl' => $transaction['redirect_url'],
        'webhook' => $transaction['webhook_url'],
        'provider' => $transaction['provider'],
        'url' => base_url().'/pay/'.$transaction['id'],
        'shortUrl' => base_url().'/p/'.$transaction['short_code'],
        'tokenizationDetails' => $transaction['tokenize'] ? [
            'tokenize' => true,
            'paymentType' => $transaction['payment_type'],
            'recurringFrequency' => $transaction['recurring_frequency'],
        ] : null,
        'paddedCardNumber' => $transaction['padded_card_number'],
        'cardExpMonth' => $transaction['card_exp_month'] === null ? null : (int) $transaction['card_exp_month'],
        'cardExpYear' => $transaction['card_exp_year'] === null ? null : (int) $transaction['card_exp_year'],
        'nextAction' => null,
        'expires' => $transaction['expires'],
        'created' => $transaction['created'],
        'updated' => $transaction['updated'],
    ];
}

function token_json(array $token): array
{
    return [
        'id' => $token['id'],
        'customerId' => $token['customer_id'],
        'brand' => $token['brand'],
        'paddedCardNumber' => $token['padded_card_number'],
        'tokenExpiryMonth' => (int) $token['exp_month'],
        'tokenExpiryYear' => (int) $token['exp_year'],
        'tokenAgreementType' => $token['agreement_type'],
        'deleted' => (bool) $token['deleted'],
        'created' => $token['created'],
    ];
}

function is_payable(array $transaction): bool
{
    return in_array($transaction['state'], PENDING_STATES, true) && $transaction['expires'] > now();
}

/**
 * Moves a pending transaction to its final state and tells the merchant, as BML does.
 */
function settle(array $transaction, string $state, ?array $card = null, ?array $token = null): array
{
    query(
        'update transactions set state = ?, token_id = ?, padded_card_number = ?, card_exp_month = ?, card_exp_year = ?, updated = ? where id = ?',
        [
            $state,
            $token['id'] ?? null,
            $card['padded_card_number'] ?? null,
            $card['exp_month'] ?? null,
            $card['exp_year'] ?? null,
            now(),
            $transaction['id'],
        ],
    );

    $settled = find('transactions', $transaction['id']);

    send_webhook($settled, [
        'eventType' => 'NOTIFY_TRANSACTION_CHANGE',
        'transactionId' => $settled['id'],
        'state' => $settled['state'],
        'amount' => (int) $settled['amount'],
        'currency' => $settled['currency'],
    ]);

    return $settled;
}

/**
 * Paying on the hosted page. A card is saved only when the payment goes through.
 */
function pay_on_hosted_page(array $transaction, string $cardNumber): array
{
    $outcome = TEST_CARDS[$cardNumber]['first'] === 'decline' ? 'FAILED' : 'CONFIRMED';
    $card = [
        'padded_card_number' => padded_card_number($cardNumber),
        'exp_month' => (int) gmdate('n'),
        'exp_year' => (int) gmdate('Y') + ((TEST_CARDS[$cardNumber]['expired'] ?? false) ? -1 : 3),
    ];

    $token = $outcome === 'CONFIRMED' && $transaction['tokenize'] && $transaction['customer_id'] !== null
        ? save_card($transaction, $cardNumber, $card)
        : null;

    $settled = settle($transaction, $outcome, $card, $token);

    if ($transaction['tokenize'] && $transaction['customer_id'] !== null) {
        send_webhook($settled, [
            'eventType' => 'NOTIFY_TOKENISATION_STATUS',
            'customerId' => $settled['customer_id'],
            'transactionId' => $settled['id'],
            'tokenisationStatus' => $token === null ? 'FAILED' : 'SUCCESS',
        ]);
    }

    return $settled;
}

function save_card(array $transaction, string $cardNumber, array $card): array
{
    $id = new_id();
    query(
        'insert into tokens (id, customer_id, card_number, brand, padded_card_number, exp_month, exp_year, agreement_type, created) values (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [
            $id,
            $transaction['customer_id'],
            $cardNumber,
            TEST_CARDS[$cardNumber]['brand'],
            $card['padded_card_number'],
            $card['exp_month'],
            $card['exp_year'],
            $transaction['payment_type'] ?? 'UNSCHEDULED',
            now(),
        ],
    );

    return find('tokens', $id);
}

/**
 * A charge on a saved card settles at once: no 3DS, no hosted page.
 */
function charge_saved_card(array $transaction, array $token): array
{
    $expired = sprintf('%04d-%02d', $token['exp_year'], $token['exp_month']) < gmdate('Y-m');
    $declines = $expired || $token['fail_next_charge'] || TEST_CARDS[$token['card_number']]['later'] === 'decline';

    if ($token['fail_next_charge']) {
        query('update tokens set fail_next_charge = 0 where id = ?', [$token['id']]);
    }

    return settle($transaction, $declines ? 'FAILED' : 'CONFIRMED', [
        'padded_card_number' => $token['padded_card_number'],
        'exp_month' => $token['exp_month'],
        'exp_year' => $token['exp_year'],
    ], $token);
}

/**
 * The query string BML appends to `redirectUrl`. Merchants must not trust it; they read the transaction.
 * The signature here follows the v1 PHP SDK's request signature, as BML documents none for the redirect.
 */
function redirect_back_url(array $transaction): string
{
    $signature = sha1('amount='.$transaction['amount'].'&currency='.$transaction['currency'].'&apiKey='.config('api_key'));
    $separator = str_contains((string) $transaction['redirect_url'], '?') ? '&' : '?';

    return $transaction['redirect_url'].$separator.http_build_query([
        'transactionId' => $transaction['id'],
        'state' => $transaction['state'],
        'signature' => $signature,
    ]);
}
