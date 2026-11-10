# BML Connect Faker

A local stand-in for the [Bank of Maldives Connect](https://bankofmaldives.stoplight.io/docs/bml-connect) v2 API, for building and testing BML payments before you have merchant UAT access, or without hitting UAT on every run.

- The same paths and fields as BML Connect v2: customers, transactions, saved cards (tokens), charging a saved card.
- A hosted payment page with test cards that pay, decline, expire, or ask for 3D Secure.
- Signed webhooks posted back to your app, with BML's headers and signature.
- A dashboard to inspect everything and to make a saved card's next charge fail, expire a card, or resend a webhook.
- Runs on whichever of PHP, Node or Python you already have. No packages to install, no build step, no services to run.
- For development and testing only. It has no real security and must not be exposed to the internet or used in production.

> Not affiliated with or endorsed by Bank of Maldives. Behaviour follows BML's public documentation; where the documentation is silent, the faker makes a choice. Those choices are listed in [What the faker guesses](#what-the-faker-guesses). Always confirm against BML's UAT before going live.

## Quick start

```sh
git clone https://github.com/Z3d0X/bml-connect-faker.git
cd bml-connect-faker
```

Then start it with the runtime you have. The three implementations behave the same and share one database file, so you can switch between them.

| You have | Run |
| --- | --- |
| PHP 8.2+ | `php -S 127.0.0.1:8787 src/php/server.php` |
| Node 22.13+ | `node src/node/server.mjs` |
| Python 3.8+ | `python3 src/python/server.py` |

Open <http://127.0.0.1:8787> for the dashboard. The SQLite database is created on the first request.

Point your app's BML base URL at `http://127.0.0.1:8787` instead of `https://api.uat.merchants.bankofmaldives.com.mv`, and send `test-api-key` as the `Authorization` header.

### With Laravel Herd or Valet

```sh
cd bml-connect-faker
herd link bml-connect-faker     # http://bml-connect-faker.test
```

Herd and Valet serve `public/index.php` by themselves. HTTPS webhooks to your other `*.test` sites work out of the box, because the faker trusts Herd's local certificate authority.

### With Docker

```sh
docker run --rm -p 8787:8787 -v "$PWD":/app -w /app php:8.3-cli php -S 0.0.0.0:8787 src/php/server.php
```

## Configuration

Every setting has a default and can be changed with an environment variable. Under Herd or Valet, where environment variables are awkward, create a `config.local.php` (gitignored) in the project root that returns the keys you want to change:

```php
<?php

return [
    'api_key' => 'my-local-key',
    'webhook_url' => 'https://my-app.test/webhooks/bml',
];
```

| Key | Environment variable | Default | What it does |
| --- | --- | --- | --- |
| `api_key` | `BML_FAKER_API_KEY` | `test-api-key` | Expected in the `Authorization` header. Also signs webhooks. |
| `webhook_url` | `BML_FAKER_WEBHOOK_URL` | none | Stands in for the webhook URL set in the BML merchant dashboard. |
| `database` | `BML_FAKER_DATABASE` | `storage/bml-connect-faker.sqlite` | The SQLite file. |
| `ca_file` | `BML_FAKER_CA_FILE` | Herd's CA, if present | An extra certificate authority for HTTPS webhook targets, such as mkcert's. |
| `transaction_lifetime_days` | `BML_FAKER_TRANSACTION_LIFETIME_DAYS` | `7` | How long a transaction can be paid, as BML's default. |

The Node and Python servers read the environment variables only, not `config.local.php`. They listen on `127.0.0.1:8787`; change that with `BML_FAKER_HOST` and `BML_FAKER_PORT`.

## How a payment flows

1. Your app creates a transaction (`POST /public/v2/transactions`). To save the card for later charges, it passes a customer and `tokenizationDetails.tokenize: true`.
2. Your app sends the customer to the returned `url`, the hosted payment page.
3. The customer picks a test card and pays or cancels.
4. The faker posts webhooks to your app, then redirects the customer to your `redirectUrl` with `transactionId`, `state` and `signature`.
5. Your app reads the transaction (`GET /public/v2/transactions/{id}`) for the real state. The redirect and the webhook only say when to look.
6. Later, your app charges the saved card: it creates a plain transaction for the amount, then calls `POST /public-customers/charge`. The charge settles at once.

The full endpoint reference is in [docs/api.md](docs/api.md), and webhooks are covered in [docs/webhooks.md](docs/webhooks.md).

## Test cards

| Card | On the hosted page | Later charges on the saved card |
| --- | --- | --- |
| `4111 1111 1111 1111` Visa | Pays | Pay |
| `5555 5555 5555 4444` Mastercard | Pays | Pay |
| `4000 0000 0000 0341` Visa | Pays | Decline |
| `4000 0000 0000 3220` Visa | Asks for 3D Secure (Approve or Reject), then pays | Pay |
| `4000 0000 0000 0002` Visa | Declined | — |
| `4000 0000 0000 0069` Visa | Declined (expired card) | — |

A card is saved only when the payment goes through and the transaction asked for `tokenize` with a customer. A card that declines on the hosted page saves nothing.

The dashboard adds two switches on each saved card: **Fail next charge**, for one failed renewal, and **Expire card**, which declines every charge until the card is replaced.

## What the faker guesses

BML's documentation doesn't show everything. Where it is silent, the faker does the following. Confirm these on UAT:

- **Response shapes.** Fields follow the documentation; anything beyond that is the faker's choice. The token list is a plain JSON array.
- **Errors.** They come back as `{"message": "…"}` with a 4xx status.
- **Webhook bodies.** The event name is in an `eventType` field. `tokenisationStatus` is `SUCCESS` or `FAILED`.
- **`X-Signature-Timestamp`** is in Unix seconds.
- **The redirect `signature`.** BML documents none for the redirect, so the faker reuses the v1 request signature, `sha1("amount=…&currency=…&apiKey=…")`. Don't trust it; read the transaction.
- **Webhook retries.** The faker sends each webhook once. Resend by hand from the dashboard.
- **Saved-card charges** never ask for 3D Secure.
- **`provider`** is stored and echoed but doesn't limit the hosted page.

Spotted a difference from the real API? Please open an issue with what BML returned.

## Project layout

```
src/php/              the PHP implementation
src/node/             the Node implementation
src/python/           the Python implementation
shared/               what all three read: schema, test cards, HTML
tests/conformance.py  the checks every implementation must pass
public/index.php      one line that loads src/php/server.php, for Herd and Valet
```

Each implementation has the same seven files with the same functions in each, and a README of its own:

| File | What it holds |
| --- | --- |
| `server` | routes; the file you run |
| `config` | defaults and environment variables |
| `bootstrap` | database and helpers |
| `api` | the BML Connect endpoints |
| `payments` | transactions, saved cards, charging |
| `webhooks` | signed webhook delivery |
| `pages` | hosted payment page and dashboard |

A change in behaviour belongs in all three implementations. What doesn't differ by language is in `shared/` and is changed once; [shared/README.md](shared/README.md) describes the files, including how to add a test card. To check that they still agree, run:

```sh
python3 tests/conformance.py
```

It starts each implementation whose runtime is installed on a free port with a throwaway database, then drives the API, the hosted page and the dashboard and checks the webhooks it receives.

## License

[MIT](LICENSE)
