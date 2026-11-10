# API reference

Every endpoint needs the API key in the `Authorization` header, sent as it is with no `Bearer` prefix. A wrong or missing key gets `401 {"message": "Unauthorized"}`.

Request and response bodies are JSON. Amounts are integers in minor units: `1000` is MVR 10.00. Errors come back as `{"message": "…"}` with a 4xx status.

| Method | Path | |
| --- | --- | --- |
| `POST` | `/public-customers` | [Create a customer](#create-a-customer) |
| `POST` | `/public/v2/transactions` | [Create a transaction](#create-a-transaction) |
| `GET` | `/public/v2/transactions/{id}` | [Read a transaction](#read-a-transaction) |
| `POST` | `/public/transactions/{id}/cancel` | [Cancel a transaction](#cancel-a-transaction) |
| `GET` | `/public-customers/{customerId}/tokens` | [List saved cards](#list-saved-cards) |
| `POST` | `/public-customers/charge` | [Charge a saved card](#charge-a-saved-card) |
| `DELETE` | `/public-customers/{customerId}/tokens/{tokenId}` | [Delete a saved card](#delete-a-saved-card) |
| `POST` | `/public/webhooks` | [Register a webhook](#register-a-webhook) |

## Create a customer

`POST /public-customers`

```json
{ "name": "Acme Pvt Ltd", "email": "billing@acme.example" }
```

`name` and `email` are required. Any other fields, such as a billing address or `taxId`, are stored and echoed back.

**201**

```json
{
    "name": "Acme Pvt Ltd",
    "email": "billing@acme.example",
    "id": "6482c3b0dd653100088ab08b",
    "created": "2026-11-10T08:00:00.000Z"
}
```

## Create a transaction

`POST /public/v2/transactions`

```json
{
    "amount": 100,
    "currency": "MVR",
    "customerId": "6482c3b0dd653100088ab08b",
    "localId": "order-1042",
    "redirectUrl": "https://my-app.test/billing/return",
    "webhook": "https://my-app.test/webhooks/bml",
    "customerAsPayer": true,
    "tokenizationDetails": {
        "tokenize": true,
        "paymentType": "UNSCHEDULED",
        "recurringFrequency": "UNSCHEDULED"
    }
}
```

| Field | |
| --- | --- |
| `amount` | Required. A positive integer in minor units. |
| `currency` | Required. |
| `customerId` | An existing customer. You can pass an inline `customer` object (`name`, `email`) instead, which creates one. |
| `localId`, `customerReference` | Your own references, echoed back. |
| `redirectUrl` | Where the hosted page sends the customer afterwards. Without it, the page shows the result. |
| `webhook` | Gets this transaction's webhooks, on top of the configured and registered ones. |
| `tokenizationDetails` | `tokenize: true` saves the card once the payment goes through. It needs a customer. `paymentType` and `recurringFrequency` default to `UNSCHEDULED`. |
| `provider` | Stored and echoed, but ignored. |

**201** returns the [transaction](#the-transaction-object) in state `QR_CODE_GENERATED`. Send the customer to `url`, or to `shortUrl`, which redirects there.

## Read a transaction

`GET /public/v2/transactions/{id}`

**200** returns the [transaction](#the-transaction-object). **404** if it doesn't exist.

Treat this as the only source of truth. The redirect's query string and the webhook body can be forged; this response can't.

## Cancel a transaction

`POST /public/transactions/{id}/cancel`

Cancels a pending transaction. **200** returns it in state `CANCELLED` and sends `NOTIFY_TRANSACTION_CHANGE`. **400** if it has already settled.

## List saved cards

`GET /public-customers/{customerId}/tokens`

**200** returns the customer's saved cards that haven't been deleted. **404** if the customer doesn't exist.

```json
[
    {
        "id": "1f51adf6e08d9987d9dbbe32",
        "customerId": "6482c3b0dd653100088ab08b",
        "brand": "VISA",
        "paddedCardNumber": "411111******1111",
        "tokenExpiryMonth": 11,
        "tokenExpiryYear": 2029,
        "tokenAgreementType": "UNSCHEDULED",
        "deleted": false,
        "created": "2026-11-10T08:01:00.000Z"
    }
]
```

## Charge a saved card

`POST /public-customers/charge`

First create a plain transaction for the amount (no `tokenizationDetails`). Then:

```json
{
    "customerId": "6482c3b0dd653100088ab08b",
    "transactionId": "73bc53a7b88ae08d8c7fba1c",
    "tokenId": "1f51adf6e08d9987d9dbbe32"
}
```

All three fields are required. The charge settles at once, with no 3D Secure and no hosted page. **200** returns the transaction as `CONFIRMED` or `FAILED` and sends `NOTIFY_TRANSACTION_CHANGE`.

It declines when:
- the card is `4000 0000 0000 0341`
- the card has expired
- **Fail next charge** is switched on for the card (this applies once)

Errors:
- **404**: the card isn't this customer's, or has been deleted.
- **422**: the transaction belongs to another customer.
- **400**: the transaction has already settled or expired.

## Delete a saved card

`DELETE /public-customers/{customerId}/tokens/{tokenId}`

**204** on success. **404** if the card isn't this customer's or is already deleted.

## Register a webhook

`POST /public/webhooks`

```json
{ "hookUrl": "https://my-app.test/webhooks/bml" }
```

**201** returns `{ "id": "…", "hookUrl": "…" }`. Every transaction's webhooks then go to this URL too.

## The transaction object

```json
{
    "id": "73bc53a7b88ae08d8c7fba1c",
    "amount": 100,
    "currency": "MVR",
    "state": "CONFIRMED",
    "customerId": "6482c3b0dd653100088ab08b",
    "localId": "order-1042",
    "customerReference": null,
    "redirectUrl": "https://my-app.test/billing/return",
    "webhook": "https://my-app.test/webhooks/bml",
    "provider": null,
    "url": "http://127.0.0.1:8787/pay/73bc53a7b88ae08d8c7fba1c",
    "shortUrl": "http://127.0.0.1:8787/p/4abd63c645",
    "tokenizationDetails": { "tokenize": true, "paymentType": "UNSCHEDULED", "recurringFrequency": "UNSCHEDULED" },
    "paddedCardNumber": "411111******1111",
    "cardExpMonth": 11,
    "cardExpYear": 2029,
    "nextAction": null,
    "expires": "2026-11-17T08:00:00.000Z",
    "created": "2026-11-10T08:00:00.000Z",
    "updated": "2026-11-10T08:01:00.000Z"
}
```

States:
- `QR_CODE_GENERATED`: pending. BML uses this name for card payments too.
- `CONFIRMED`: paid.
- `FAILED`: declined, or 3D Secure rejected.
- `CANCELLED`: the customer or your app cancelled it.

A pending transaction can be paid until `expires`, 7 days after it's created by default.
