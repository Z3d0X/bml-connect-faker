// Transactions, saved cards, charging. Follows src/php/payments.php.

import { createHash } from 'node:crypto';

import { config } from './config.mjs';
import { TEST_CARDS, PENDING_STATES, query, find, newId, now, text, paddedCardNumber } from './bootstrap.mjs';
import { sendWebhook } from './webhooks.mjs';

export function createCustomer(input) {
    const id = newId();
    query('insert into customers (id, name, email, payload, created) values (?, ?, ?, ?, ?)', [
        id, text(input.name), text(input.email), JSON.stringify(input), now(),
    ]);

    return find('customers', id);
}

export function customerJson(customer) {
    return {
        ...JSON.parse(customer.payload),
        id: customer.id,
        name: customer.name,
        email: customer.email,
        created: customer.created,
    };
}

export function transactionJson(request, transaction) {
    return {
        id: transaction.id,
        amount: Number(transaction.amount),
        currency: transaction.currency,
        state: transaction.state,
        customerId: transaction.customer_id,
        localId: transaction.local_id,
        customerReference: transaction.customer_reference,
        redirectUrl: transaction.redirect_url,
        webhook: transaction.webhook_url,
        provider: transaction.provider,
        url: `${request.baseUrl}/pay/${transaction.id}`,
        shortUrl: `${request.baseUrl}/p/${transaction.short_code}`,
        tokenizationDetails: transaction.tokenize ? {
            tokenize: true,
            paymentType: transaction.payment_type,
            recurringFrequency: transaction.recurring_frequency,
        } : null,
        paddedCardNumber: transaction.padded_card_number,
        cardExpMonth: transaction.card_exp_month === null ? null : Number(transaction.card_exp_month),
        cardExpYear: transaction.card_exp_year === null ? null : Number(transaction.card_exp_year),
        nextAction: null,
        expires: transaction.expires,
        created: transaction.created,
        updated: transaction.updated,
    };
}

export function tokenJson(token) {
    return {
        id: token.id,
        customerId: token.customer_id,
        brand: token.brand,
        paddedCardNumber: token.padded_card_number,
        tokenExpiryMonth: Number(token.exp_month),
        tokenExpiryYear: Number(token.exp_year),
        tokenAgreementType: token.agreement_type,
        deleted: Boolean(token.deleted),
        created: token.created,
    };
}

export const isPayable = (transaction) => PENDING_STATES.includes(transaction.state) && transaction.expires > now();

/** Moves a pending transaction to its final state and tells the merchant, as BML does. */
export async function settle(transaction, state, card = null, token = null) {
    query(
        'update transactions set state = ?, token_id = ?, padded_card_number = ?, card_exp_month = ?, card_exp_year = ?, updated = ? where id = ?',
        [
            state,
            token?.id ?? null,
            card?.padded_card_number ?? null,
            card?.exp_month ?? null,
            card?.exp_year ?? null,
            now(),
            transaction.id,
        ],
    );

    const settled = find('transactions', transaction.id);

    await sendWebhook(settled, {
        eventType: 'NOTIFY_TRANSACTION_CHANGE',
        transactionId: settled.id,
        state: settled.state,
        amount: Number(settled.amount),
        currency: settled.currency,
    });

    return settled;
}

/** Paying on the hosted page. A card is saved only when the payment goes through. */
export async function payOnHostedPage(transaction, cardNumber) {
    const outcome = TEST_CARDS.get(cardNumber).first === 'decline' ? 'FAILED' : 'CONFIRMED';
    const today = new Date();
    const card = {
        padded_card_number: paddedCardNumber(cardNumber),
        exp_month: today.getUTCMonth() + 1,
        exp_year: today.getUTCFullYear() + (TEST_CARDS.get(cardNumber).expired ? -1 : 3),
    };
    const saves = Boolean(transaction.tokenize) && transaction.customer_id !== null;

    const token = outcome === 'CONFIRMED' && saves ? saveCard(transaction, cardNumber, card) : null;

    const settled = await settle(transaction, outcome, card, token);

    if (saves) {
        await sendWebhook(settled, {
            eventType: 'NOTIFY_TOKENISATION_STATUS',
            customerId: settled.customer_id,
            transactionId: settled.id,
            tokenisationStatus: token === null ? 'FAILED' : 'SUCCESS',
        });
    }

    return settled;
}

function saveCard(transaction, cardNumber, card) {
    const id = newId();
    query(
        'insert into tokens (id, customer_id, card_number, brand, padded_card_number, exp_month, exp_year, agreement_type, created) values (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [
            id,
            transaction.customer_id,
            cardNumber,
            TEST_CARDS.get(cardNumber).brand,
            card.padded_card_number,
            card.exp_month,
            card.exp_year,
            transaction.payment_type ?? 'UNSCHEDULED',
            now(),
        ],
    );

    return find('tokens', id);
}

/** A charge on a saved card settles at once: no 3DS, no hosted page. */
export async function chargeSavedCard(transaction, token) {
    const expiry = `${String(token.exp_year).padStart(4, '0')}-${String(token.exp_month).padStart(2, '0')}`;
    const expired = expiry < now().slice(0, 7);
    const declines = expired || Boolean(token.fail_next_charge) || TEST_CARDS.get(token.card_number)?.later === 'decline';

    if (token.fail_next_charge) {
        query('update tokens set fail_next_charge = 0 where id = ?', [token.id]);
    }

    return settle(transaction, declines ? 'FAILED' : 'CONFIRMED', {
        padded_card_number: token.padded_card_number,
        exp_month: token.exp_month,
        exp_year: token.exp_year,
    }, token);
}

/*
 * The query string BML appends to `redirectUrl`. Merchants must not trust it; they read the transaction.
 * The signature here follows the v1 PHP SDK's request signature, as BML documents none for the redirect.
 */
export function redirectBackUrl(transaction) {
    const signature = createHash('sha1')
        .update(`amount=${transaction.amount}&currency=${transaction.currency}&apiKey=${config.apiKey}`)
        .digest('hex');
    const separator = transaction.redirect_url.includes('?') ? '&' : '?';

    return transaction.redirect_url + separator + new URLSearchParams({
        transactionId: transaction.id,
        state: transaction.state,
        signature,
    });
}
