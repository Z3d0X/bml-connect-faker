# Webhooks

The faker POSTs JSON to every webhook target:

1. the transaction's own `webhook` field
2. every URL registered through `POST /public/webhooks`
3. the configured `webhook_url`, which stands in for the merchant dashboard setting

Each delivery is logged on the dashboard with the response status, and you can resend it from there. Each webhook is sent once, with no automatic retries.

## Events

`NOTIFY_TRANSACTION_CHANGE` is sent when a transaction reaches a final state: paid, declined, cancelled, or charged on a saved card.

```json
{
    "eventType": "NOTIFY_TRANSACTION_CHANGE",
    "transactionId": "73bc53a7b88ae08d8c7fba1c",
    "state": "CONFIRMED",
    "amount": 100,
    "currency": "MVR"
}
```

`NOTIFY_TOKENISATION_STATUS` is sent after a hosted payment that asked to save the card. It reports `SUCCESS` when the card was saved and `FAILED` when the payment didn't go through.

```json
{
    "eventType": "NOTIFY_TOKENISATION_STATUS",
    "customerId": "6482c3b0dd653100088ab08b",
    "transactionId": "73bc53a7b88ae08d8c7fba1c",
    "tokenisationStatus": "SUCCESS"
}
```

## Headers and signature

```
Content-Type: application/json
X-Originator: PomeloPay-Webhooks
X-Signature-Nonce: 5f0c…
X-Signature-Timestamp: 1794227252
X-Signature: sha256(nonce + timestamp + apiKey), hex
```

As in BML Connect, the signature covers the nonce, the timestamp and your API key. **It doesn't cover the body.** A valid signature only proves the request came from someone who knows your key. So treat the body as a hint: take the `transactionId` and read the transaction from the API before you act.

## Verifying in your app

PHP:

```php
$nonce = $request->header('X-Signature-Nonce');
$timestamp = $request->header('X-Signature-Timestamp');
$expected = hash('sha256', $nonce.$timestamp.$apiKey);

if (! hash_equals($expected, strtolower($request->header('X-Signature')))) {
    abort(401);
}

$transaction = $bml->getTransaction($request->input('transactionId')); // the real state
```

Node:

```js
import { createHash, timingSafeEqual } from 'node:crypto';

const expected = createHash('sha256')
    .update(req.headers['x-signature-nonce'] + req.headers['x-signature-timestamp'] + apiKey)
    .digest('hex');
const received = String(req.headers['x-signature'] ?? '').toLowerCase();

if (received.length !== expected.length || !timingSafeEqual(Buffer.from(received), Buffer.from(expected))) {
    return res.sendStatus(401);
}
```

Python:

```python
import hashlib
import hmac

expected = hashlib.sha256(
    (request.headers['X-Signature-Nonce'] + request.headers['X-Signature-Timestamp'] + api_key).encode()
).hexdigest()

if not hmac.compare_digest(expected, request.headers.get('X-Signature', '').lower()):
    abort(401)
```

## HTTPS targets

Webhooks to `https://` URLs use the system's certificate authorities, plus `ca_file`. By default `ca_file` is Herd's local CA, so `https://*.test` sites served by Herd work. For mkcert, set `BML_FAKER_CA_FILE` to `$(mkcert -CAROOT)/rootCA.pem`.
