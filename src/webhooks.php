<?php

declare(strict_types=1);

/**
 * Sends the event to the transaction's own webhook, every registered webhook and the configured one.
 */
function send_webhook(array $transaction, array $payload): void
{
    $registered = array_column(query('select hook_url from webhooks')->fetchAll(), 'hook_url');
    $targets = array_unique(array_filter([$transaction['webhook_url'], ...$registered, config('webhook_url')]));

    foreach ($targets as $url) {
        deliver($url, json_encode($payload, JSON_UNESCAPED_SLASHES));
    }
}

/**
 * BML signs the headers only: sha256(nonce + timestamp + apiKey). The body is not covered.
 */
function deliver(string $url, string $body): void
{
    $nonce = bin2hex(random_bytes(16));
    $timestamp = (string) time();

    $curl = curl_init($url);
    $options = [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => $body,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 10,
        CURLOPT_HTTPHEADER => [
            'Content-Type: application/json',
            'X-Originator: PomeloPay-Webhooks',
            'X-Signature-Nonce: '.$nonce,
            'X-Signature-Timestamp: '.$timestamp,
            'X-Signature: '.hash('sha256', $nonce.$timestamp.config('api_key')),
        ],
    ];

    if (is_file((string) config('ca_file'))) {
        $options[CURLOPT_CAINFO] = config('ca_file');
    }

    curl_setopt_array($curl, $options);
    $response = curl_exec($curl);
    $status = curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    $error = curl_error($curl);

    query('insert into deliveries (url, body, status, response, created) values (?, ?, ?, ?, ?)', [
        $url,
        $body,
        $status === 0 ? null : $status,
        $response === false ? $error : substr((string) $response, 0, 2000),
        now(),
    ]);
}
