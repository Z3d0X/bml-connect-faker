# Python implementation

Needs Python 3.8+. No packages to install.

```sh
python3 src/python/server.py
```

It listens on `127.0.0.1:8787`; change that with `BML_FAKER_HOST` and `BML_FAKER_PORT`. The other settings are the environment variables in the main README.

## Files

| File | What it holds |
| --- | --- |
| `server.py` | routes; the file you run |
| `config.py` | defaults and environment variables |
| `bootstrap.py` | database and helpers |
| `api.py` | the BML Connect endpoints |
| `payments.py` | transactions, saved cards, charging |
| `webhooks.py` | signed webhook delivery |
| `pages.py` | hosted payment page and dashboard |

The PHP and Node implementations have the same files with the same functions. A change in behaviour here belongs in all three; `python3 tests/conformance.py` checks that they agree.

## Only in Python

- It does not read `config.local.php`.
