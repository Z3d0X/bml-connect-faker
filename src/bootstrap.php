<?php

declare(strict_types=1);

const ROOT = __DIR__.'/..';

/**
 * Test cards on the hosted page. `first` is what paying on the hosted page does,
 * `later` what a charge on the saved card does.
 */
const TEST_CARDS = [
    '4111111111111111' => ['brand' => 'VISA', 'label' => 'Pays', 'first' => 'pay', 'later' => 'pay'],
    '5555555555554444' => ['brand' => 'MASTERCARD', 'label' => 'Pays', 'first' => 'pay', 'later' => 'pay'],
    '4000000000000341' => ['brand' => 'VISA', 'label' => 'Pays now, every later charge declines', 'first' => 'pay', 'later' => 'decline'],
    '4000000000003220' => ['brand' => 'VISA', 'label' => 'Asks for 3DS on this page, then pays', 'first' => '3ds', 'later' => 'pay'],
    '4000000000000002' => ['brand' => 'VISA', 'label' => 'Declined', 'first' => 'decline', 'later' => 'decline'],
    '4000000000000069' => ['brand' => 'VISA', 'label' => 'Expired card', 'first' => 'decline', 'later' => 'decline'],
];

const PENDING_STATES = ['INITIATED', 'QR_CODE_GENERATED'];

function config(string $key): mixed
{
    static $config = null;

    if ($config === null) {
        $local = ROOT.'/config.local.php';
        $config = array_replace(require ROOT.'/config.php', is_file($local) ? require $local : []);
    }

    return $config[$key] ?? null;
}

function db(): PDO
{
    static $pdo = null;

    if ($pdo instanceof PDO) {
        return $pdo;
    }

    $path = (string) config('database');

    if (! is_dir(dirname($path))) {
        mkdir(dirname($path), 0775, true);
    }

    $pdo = new PDO('sqlite:'.$path, options: [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
    $pdo->exec(file_get_contents(ROOT.'/src/schema.sql'));

    return $pdo;
}

function query(string $sql, array $bindings = []): PDOStatement
{
    $statement = db()->prepare($sql);
    $statement->execute($bindings);

    return $statement;
}

function find(string $table, string $id): ?array
{
    $row = query("select * from {$table} where id = ?", [$id])->fetch();

    return $row === false ? null : $row;
}

/** Ids look like BML's: 24 hex characters. */
function new_id(): string
{
    return bin2hex(random_bytes(12));
}

function now(): string
{
    return gmdate('Y-m-d\TH:i:s.v\Z');
}

function base_url(): string
{
    $scheme = ($_SERVER['HTTPS'] ?? '') !== '' && $_SERVER['HTTPS'] !== 'off' ? 'https' : 'http';

    return $scheme.'://'.($_SERVER['HTTP_HOST'] ?? 'localhost');
}

function json_body(): array
{
    $decoded = json_decode((string) file_get_contents('php://input'), true);

    return is_array($decoded) ? $decoded : [];
}

function respond_json(mixed $data, int $status = 200): never
{
    http_response_code($status);
    header('Content-Type: application/json');
    echo json_encode($data, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    exit;
}

function fail(int $status, string $message): never
{
    respond_json(['message' => $message], $status);
}

function respond_html(string $html, int $status = 200): never
{
    http_response_code($status);
    header('Content-Type: text/html; charset=utf-8');
    echo $html;
    exit;
}

function redirect(string $url): never
{
    header('Location: '.$url, true, 303);
    exit;
}

function e(mixed $value): string
{
    return htmlspecialchars((string) $value, ENT_QUOTES);
}

function padded_card_number(string $number): string
{
    return substr($number, 0, 6).str_repeat('*', strlen($number) - 10).substr($number, -4);
}
