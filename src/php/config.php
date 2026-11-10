<?php

declare(strict_types=1);

/*
 * Defaults, each overridable by an environment variable. To change them without environment
 * variables (under Herd or Valet, say), create config.local.php in the project root, returning an array of the same keys.
 */
return [
    // The value clients send in the Authorization header. It also signs webhooks.
    'api_key' => getenv('BML_FAKER_API_KEY') ?: 'test-api-key',

    // Stands in for the webhook URL set in the BML merchant dashboard. Webhooks also go to the
    // transaction's own `webhook` and to every URL registered through POST /public/webhooks.
    'webhook_url' => getenv('BML_FAKER_WEBHOOK_URL') ?: null,

    'database' => getenv('BML_FAKER_DATABASE') ?: dirname(__DIR__, 2).'/storage/bml-connect-faker.sqlite',

    // Extra certificate authority for HTTPS webhook targets, such as Herd's or mkcert's local CA.
    'ca_file' => getenv('BML_FAKER_CA_FILE') ?: getenv('HOME').'/Library/Application Support/Herd/config/valet/CA/LaravelValetCASelfSigned.pem',

    // How long a transaction can be paid, as BML's default.
    'transaction_lifetime_days' => (int) (getenv('BML_FAKER_TRANSACTION_LIFETIME_DAYS') ?: 7),
];
