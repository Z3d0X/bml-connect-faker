# Node implementation

Needs Node 22.13+ (for the built-in `node:sqlite`). No packages to install.

```sh
node src/node/server.mjs
```

It listens on `127.0.0.1:8787`; change that with `BML_FAKER_HOST` and `BML_FAKER_PORT`. The other settings are the environment variables in the main README.

## Files

| File | What it holds |
| --- | --- |
| `server.mjs` | routes; the file you run |
| `config.mjs` | defaults and environment variables |
| `bootstrap.mjs` | database and helpers |
| `api.mjs` | the BML Connect endpoints |
| `payments.mjs` | transactions, saved cards, charging |
| `webhooks.mjs` | signed webhook delivery |
| `pages.mjs` | hosted payment page and dashboard |

The PHP and Python implementations have the same files with the same functions. A change in behaviour here belongs in all three; `python3 tests/conformance.py` checks that they agree.

## Only in Node

- It does not read `config.local.php`.
- An amount written as `100.0` is accepted, because JavaScript cannot tell it from `100`. PHP and Python reject it.
