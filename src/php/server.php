<?php

declare(strict_types=1);

/*
 * BML Connect Faker in PHP. Needs PHP 8.2+ and nothing else.
 *
 *     php -S 127.0.0.1:8787 src/php/server.php
 */

require __DIR__.'/bootstrap.php';
require __DIR__.'/payments.php';
require __DIR__.'/webhooks.php';
require __DIR__.'/api.php';
require __DIR__.'/pages.php';

// [method, path pattern, handler, needs the API key]
const ROUTES = [
    ['POST', '#^/public-customers$#', 'api_create_customer', true],
    ['POST', '#^/public-customers/charge$#', 'api_charge_token', true],
    ['GET', '#^/public-customers/([^/]+)/tokens$#', 'api_list_tokens', true],
    ['DELETE', '#^/public-customers/([^/]+)/tokens/([^/]+)$#', 'api_delete_token', true],
    ['POST', '#^/public/v2/transactions$#', 'api_create_transaction', true],
    ['GET', '#^/public/v2/transactions/([^/]+)$#', 'api_get_transaction', true],
    ['POST', '#^/public/transactions/([^/]+)/cancel$#', 'api_cancel_transaction', true],
    ['POST', '#^/public/webhooks$#', 'api_register_webhook', true],

    ['GET', '#^/pay/([^/]+)$#', 'page_pay', false],
    ['POST', '#^/pay/([^/]+)$#', 'page_pay_submit', false],
    ['GET', '#^/p/([^/]+)$#', 'page_short_link', false],

    ['GET', '#^/$#', 'page_dashboard', false],
    ['POST', '#^/dashboard/tokens/([^/]+)/fail-next$#', 'dashboard_toggle_fail_next', false],
    ['POST', '#^/dashboard/tokens/([^/]+)/expire$#', 'dashboard_expire_card', false],
    ['POST', '#^/dashboard/deliveries/([0-9]+)/resend$#', 'dashboard_resend', false],
    ['POST', '#^/dashboard/reset$#', 'dashboard_reset', false],
];

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path = rtrim((string) parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH), '/') ?: '/';

foreach (ROUTES as [$routeMethod, $pattern, $handler, $needsApiKey]) {
    if ($routeMethod === $method && preg_match($pattern, $path, $matches) === 1) {
        if ($needsApiKey) {
            authenticate();
        }

        $handler(...array_slice($matches, 1));
    }
}

fail(404, "No route for {$method} {$path}");
