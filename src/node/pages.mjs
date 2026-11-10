// Hosted payment page and dashboard. Follows src/php/pages.php.

import { TEST_CARDS, db, query, find, respondHtml, redirect, render } from './bootstrap.mjs';
import { isPayable, settle, payOnHostedPage, redirectBackUrl } from './payments.mjs';
import { deliver } from './webhooks.mjs';

/** Sends a template from shared/templates inside the layout. */
const page = (title, template, values = {}, status = 200) => respondHtml(render('layout', { title, body: render(template, values) }), status);

const formattedAmount = (transaction) => (transaction.amount / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const resultPage = (transaction) => page('Payment', 'result', { ...transaction, amount: formattedAmount(transaction) });

export function pagePay(request, id) {
    const transaction = find('transactions', id);

    if (transaction === null) {
        return page('Not found', 'message', { message: 'No such transaction.' }, 404);
    }

    if (! isPayable(transaction)) {
        return resultPage(transaction);
    }

    const options = [...TEST_CARDS.values()].map((card, index) => render('pay-option', {
        ...card,
        spaced_number: card.number.match(/.{1,4}/g).join(' '),
        checked: index === 0 ? 'checked' : '',
    })).join('');

    return page('Payment', 'pay', {
        ...transaction,
        amount: formattedAmount(transaction),
        options,
        saving_hidden: transaction.tokenize ? '' : 'hidden',
    });
}

export async function pagePaySubmit(request, id) {
    const transaction = find('transactions', id);

    if (transaction === null) {
        return page('Not found', 'message', { message: 'No such transaction.' }, 404);
    }

    if (! isPayable(transaction)) {
        return resultPage(transaction);
    }

    const form = new URLSearchParams(request.body);
    const action = form.get('action') ?? 'pay';
    const cardNumber = form.get('card') ?? '';

    if (action === 'cancel' || action === '3ds-reject') {
        return finish(await settle(transaction, action === 'cancel' ? 'CANCELLED' : 'FAILED'));
    }

    if (! TEST_CARDS.has(cardNumber)) {
        return redirect(`/pay/${id}`);
    }

    if (TEST_CARDS.get(cardNumber).first === '3ds' && action !== '3ds-approve') {
        return page('3D Secure', '3ds', { card: cardNumber });
    }

    return finish(await payOnHostedPage(transaction, cardNumber));
}

function finish(transaction) {
    if (transaction.redirect_url !== null && transaction.redirect_url !== '') {
        return redirect(redirectBackUrl(transaction));
    }

    return resultPage(transaction);
}

export function pageShortLink(request, code) {
    const transaction = query('select id from transactions where short_code = ?', [code])[0];

    return transaction === undefined ? page('Not found', 'message', { message: 'No such link.' }, 404) : redirect(`/pay/${transaction.id}`);
}

export function pageDashboard(request) {
    const transactions = query('select * from transactions order by created desc limit 50');
    const tokens = query('select tokens.*, customers.name, customers.email from tokens join customers on customers.id = tokens.customer_id order by tokens.created desc limit 50');
    const deliveries = query('select * from deliveries order by id desc limit 30');

    return page('Dashboard', 'dashboard', {
        base_url: request.baseUrl,
        transactions: transactions.map((row) => render('dashboard-transaction', {
            ...row,
            amount: formattedAmount(row),
            card: row.tokenize ? 'saves card' : (row.token_id ? 'saved card' : ''),
        })).join(''),
        tokens: tokens.map((row) => render('dashboard-token', {
            ...row,
            expiry: `${String(row.exp_month).padStart(2, '0')}/${String(row.exp_year).padStart(4, '0')}`,
            deleted_hidden: row.deleted ? '' : 'hidden',
            fail_next_label: row.fail_next_charge ? 'Next charge fails (undo)' : 'Fail next charge',
        })).join(''),
        deliveries: deliveries.map((row) => render('dashboard-delivery', {
            ...row,
            status: row.status ?? 'no answer',
        })).join(''),
    });
}

export function dashboardToggleFailNext(request, tokenId) {
    query('update tokens set fail_next_charge = 1 - fail_next_charge where id = ?', [tokenId]);

    return redirect('/');
}

export function dashboardExpireCard(request, tokenId) {
    const today = new Date();
    const lastMonth = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - 1, 1));
    query('update tokens set exp_month = ?, exp_year = ? where id = ?', [lastMonth.getUTCMonth() + 1, lastMonth.getUTCFullYear(), tokenId]);

    return redirect('/');
}

export async function dashboardResend(request, deliveryId) {
    const delivery = query('select * from deliveries where id = ?', [Number(deliveryId)])[0];

    if (delivery !== undefined) {
        await deliver(delivery.url, delivery.body);
    }

    return redirect('/');
}

export function dashboardReset() {
    for (const table of ['deliveries', 'tokens', 'transactions', 'customers', 'webhooks']) {
        db.exec(`delete from ${table}`);
    }

    return redirect('/');
}
