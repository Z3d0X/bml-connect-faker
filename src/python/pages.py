"""Hosted payment page and dashboard. Follows src/php/pages.php."""

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

from bootstrap import TEST_CARDS, request, query, find, respond_html, redirect, render
from payments import is_payable, settle, pay_on_hosted_page, redirect_back_url
from webhooks import deliver


def page(title, template, values=None, status=200):
    """Sends a template from shared/templates inside the layout."""
    return respond_html(render('layout', {'title': title, 'body': render(template, values or {})}), status)


def formatted_amount(transaction):
    return '{:,.2f}'.format(transaction['amount'] / 100)


def result_page(transaction):
    return page('Payment', 'result', {**transaction, 'amount': formatted_amount(transaction)})


def page_pay(id):
    transaction = find('transactions', id)

    if transaction is None:
        return page('Not found', 'message', {'message': 'No such transaction.'}, 404)

    if not is_payable(transaction):
        return result_page(transaction)

    options = ''.join(
        render('pay-option', {
            **card,
            'spaced_number': ' '.join(re.findall('.{1,4}', card['number'])),
            'checked': 'checked' if index == 0 else '',
        })
        for index, card in enumerate(TEST_CARDS.values())
    )

    return page('Payment', 'pay', {
        **transaction,
        'amount': formatted_amount(transaction),
        'options': options,
        'saving_hidden': '' if transaction['tokenize'] else 'hidden',
    })


def page_pay_submit(id):
    transaction = find('transactions', id)

    if transaction is None:
        return page('Not found', 'message', {'message': 'No such transaction.'}, 404)

    if not is_payable(transaction):
        return result_page(transaction)

    form = parse_qs(request.body, keep_blank_values=True)
    action = form.get('action', ['pay'])[0]
    card_number = form.get('card', [''])[0]

    if action in ('cancel', '3ds-reject'):
        return finish(settle(transaction, 'CANCELLED' if action == 'cancel' else 'FAILED'))

    if card_number not in TEST_CARDS:
        return redirect('/pay/' + id)

    if TEST_CARDS[card_number]['first'] == '3ds' and action != '3ds-approve':
        return page('3D Secure', '3ds', {'card': card_number})

    return finish(pay_on_hosted_page(transaction, card_number))


def finish(transaction):
    if transaction['redirect_url']:
        return redirect(redirect_back_url(transaction))

    return result_page(transaction)


def page_short_link(code):
    rows = query('select id from transactions where short_code = ?', [code])

    return redirect('/pay/' + rows[0]['id']) if rows else page('Not found', 'message', {'message': 'No such link.'}, 404)


def page_dashboard():
    transactions = query('select * from transactions order by created desc limit 50')
    tokens = query('select tokens.*, customers.name, customers.email from tokens join customers on customers.id = tokens.customer_id order by tokens.created desc limit 50')
    deliveries = query('select * from deliveries order by id desc limit 30')

    return page('Dashboard', 'dashboard', {
        'base_url': request.base_url,
        'transactions': ''.join(render('dashboard-transaction', {
            **row,
            'amount': formatted_amount(row),
            'card': 'saves card' if row['tokenize'] else ('saved card' if row['token_id'] else ''),
        }) for row in transactions),
        'tokens': ''.join(render('dashboard-token', {
            **row,
            'expiry': '%02d/%04d' % (row['exp_month'], row['exp_year']),
            'deleted_hidden': '' if row['deleted'] else 'hidden',
            'fail_next_label': 'Next charge fails (undo)' if row['fail_next_charge'] else 'Fail next charge',
        }) for row in tokens),
        'deliveries': ''.join(render('dashboard-delivery', {
            **row,
            'status': 'no answer' if row['status'] is None else row['status'],
        }) for row in deliveries),
    })


def dashboard_toggle_fail_next(token_id):
    query('update tokens set fail_next_charge = 1 - fail_next_charge where id = ?', [token_id])

    return redirect('/')


def dashboard_expire_card(token_id):
    last_month = datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)
    query('update tokens set exp_month = ?, exp_year = ? where id = ?', [last_month.month, last_month.year, token_id])

    return redirect('/')


def dashboard_resend(delivery_id):
    rows = query('select * from deliveries where id = ?', [int(delivery_id)])

    if rows:
        deliver(rows[0]['url'], rows[0]['body'])

    return redirect('/')


def dashboard_reset():
    for table in ('deliveries', 'tokens', 'transactions', 'customers', 'webhooks'):
        query('delete from ' + table)

    return redirect('/')
