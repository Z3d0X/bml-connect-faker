# PHP implementation

Needs PHP 8.2+ with the `pdo_sqlite` and `curl` extensions. No Composer.

```sh
php -S 127.0.0.1:8787 src/php/server.php
```

Run it from the project root. Under Laravel Herd or Valet, link the project root instead: `public/index.php` there loads `server.php`.

## Files

| File | What it holds |
| --- | --- |
| `server.php` | routes; the file you run |
| `config.php` | defaults and environment variables |
| `bootstrap.php` | database and helpers |
| `api.php` | the BML Connect endpoints |
| `payments.php` | transactions, saved cards, charging |
| `webhooks.php` | signed webhook delivery |
| `pages.php` | hosted payment page and dashboard |

The Node and Python implementations have the same files with the same functions. A change in behaviour here belongs in all three; `python3 tests/conformance.py` checks that they agree.

## Only in PHP

- Settings can also come from a `config.local.php` in the project root, which wins over environment variables.
- `php -S` serves one request at a time. If your app calls the faker back while it is handling a webhook, start it with `PHP_CLI_SERVER_WORKERS=4`.
- When the certificate authority in `ca_file` exists, HTTPS webhooks trust only that one, so they reach local sites such as `*.test` but not public HTTPS URLs.
