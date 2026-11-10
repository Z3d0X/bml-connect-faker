<?php

declare(strict_types=1);

function layout(string $title, string $body): string
{
    return <<<HTML
    <!doctype html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{$title} · BML Connect Faker</title>
    <style>
        body { font: 15px/1.5 system-ui, sans-serif; margin: 0; background: #f4f5f7; color: #1b2328; }
        main { max-width: 960px; margin: 0 auto; padding: 24px 16px; }
        .card { background: #fff; border: 1px solid #dde1e6; border-radius: 10px; padding: 20px; margin-bottom: 16px; }
        .narrow { max-width: 440px; margin: 40px auto; }
        h1 { font-size: 20px; margin: 0 0 4px; } h2 { font-size: 16px; margin: 0 0 12px; }
        .muted { color: #5b6670; font-size: 13px; }
        .amount { font-size: 28px; font-weight: 600; margin: 12px 0; }
        label.option { display: flex; gap: 10px; padding: 8px 0; border-top: 1px solid #eef0f2; }
        code { font-size: 13px; }
        button { font: inherit; padding: 8px 14px; border-radius: 8px; border: 1px solid #c5ccd3; background: #fff; cursor: pointer; }
        button.primary { background: #1b2328; border-color: #1b2328; color: #fff; }
        .notice { background: #fff8e1; border: 1px solid #f0d58a; border-radius: 8px; padding: 8px 12px; font-size: 13px; margin-bottom: 12px; }
        .actions { display: flex; gap: 8px; margin-top: 16px; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { text-align: left; padding: 6px 8px; border-top: 1px solid #eef0f2; vertical-align: top; }
        .state-CONFIRMED { color: #0a7c3a; } .state-FAILED, .state-CANCELLED { color: #b42318; }
        form.inline { display: inline; }
    </style>
    </head>
    <body><main>{$body}</main></body>
    </html>
    HTML;
}

function page_pay(string $id): never
{
    $transaction = find('transactions', $id) ?? respond_html(layout('Not found', '<div class="card narrow">No such transaction.</div>'), 404);

    if (! is_payable($transaction)) {
        respond_html(layout('Payment', result_card($transaction)));
    }

    $options = '';

    // PHP turns the numeric card keys into integers.
    foreach (TEST_CARDS as $key => $card) {
        $number = (string) $key;
        $checked = $key === array_key_first(TEST_CARDS) ? 'checked' : '';
        $options .= '<label class="option"><input type="radio" name="card" value="'.e($number).'" '.$checked.'>'
            .'<span><code>'.e(chunk_split($number, 4, ' ')).'</code> '.e($card['brand']).'<br><span class="muted">'.e($card['label']).'</span></span></label>';
    }

    $amount = formatted_amount($transaction);
    $saving = $transaction['tokenize'] ? '<p class="muted">This card will be saved for later payments ('.e($transaction['payment_type']).').</p>' : '';

    respond_html(layout('Payment', <<<HTML
        <div class="card narrow">
            <div class="notice">Test payment page from BML Connect Faker. No real card is charged.</div>
            <h1>Test payment</h1>
            <div class="muted">Transaction <code>{$transaction['id']}</code></div>
            <div class="amount">{$transaction['currency']} {$amount}</div>
            {$saving}
            <form method="post">
                {$options}
                <div class="actions">
                    <button class="primary" name="action" value="pay">Pay</button>
                    <button name="action" value="cancel">Cancel</button>
                </div>
            </form>
        </div>
        HTML));
}

function formatted_amount(array $transaction): string
{
    return number_format($transaction['amount'] / 100, 2);
}

function page_pay_submit(string $id): never
{
    $transaction = find('transactions', $id) ?? respond_html(layout('Not found', '<div class="card narrow">No such transaction.</div>'), 404);

    if (! is_payable($transaction)) {
        respond_html(layout('Payment', result_card($transaction)));
    }

    $action = $_POST['action'] ?? 'pay';
    $cardNumber = (string) ($_POST['card'] ?? '');

    if ($action === 'cancel' || $action === '3ds-reject') {
        finish(settle($transaction, $action === 'cancel' ? 'CANCELLED' : 'FAILED'));
    }

    if (! isset(TEST_CARDS[$cardNumber])) {
        redirect('/pay/'.$id);
    }

    if (TEST_CARDS[$cardNumber]['first'] === '3ds' && $action !== '3ds-approve') {
        respond_html(layout('3D Secure', <<<HTML
            <div class="card narrow">
                <h1>3D Secure check</h1>
                <p class="muted">The bank asks the cardholder to confirm this payment.</p>
                <form method="post">
                    <input type="hidden" name="card" value="{$cardNumber}">
                    <div class="actions">
                        <button class="primary" name="action" value="3ds-approve">Approve</button>
                        <button name="action" value="3ds-reject">Reject</button>
                    </div>
                </form>
            </div>
            HTML));
    }

    finish(pay_on_hosted_page($transaction, $cardNumber));
}

function finish(array $transaction): never
{
    if ($transaction['redirect_url'] !== null && $transaction['redirect_url'] !== '') {
        redirect(redirect_back_url($transaction));
    }

    respond_html(layout('Payment', result_card($transaction)));
}

function result_card(array $transaction): string
{
    return '<div class="card narrow"><h1>Payment <span class="state-'.e($transaction['state']).'">'.e($transaction['state']).'</span></h1>'
        .'<div class="muted">'.e($transaction['currency']).' '.formatted_amount($transaction).' · <code>'.e($transaction['id']).'</code></div></div>';
}

function page_short_link(string $code): never
{
    $transaction = query('select id from transactions where short_code = ?', [$code])->fetch();

    $transaction === false ? respond_html(layout('Not found', '<div class="card narrow">No such link.</div>'), 404) : redirect('/pay/'.$transaction['id']);
}

function page_dashboard(): never
{
    $transactions = query('select * from transactions order by created desc limit 50')->fetchAll();
    $tokens = query('select tokens.*, customers.name, customers.email from tokens join customers on customers.id = tokens.customer_id order by tokens.created desc limit 50')->fetchAll();
    $deliveries = query('select * from deliveries order by id desc limit 30')->fetchAll();

    $transactionRows = implode('', array_map(fn (array $row): string => '<tr><td><a href="/pay/'.e($row['id']).'"><code>'.e($row['id']).'</code></a></td>'
        .'<td>'.e($row['currency']).' '.formatted_amount($row).'</td><td class="state-'.e($row['state']).'">'.e($row['state']).'</td>'
        .'<td>'.e($row['local_id']).'</td><td>'.($row['tokenize'] ? 'saves card' : ($row['token_id'] ? 'saved card' : '')).'</td><td class="muted">'.e($row['updated']).'</td></tr>', $transactions));

    $tokenRows = implode('', array_map(fn (array $row): string => '<tr><td><code>'.e($row['id']).'</code></td><td>'.e($row['name']).'<br><span class="muted">'.e($row['email']).'</span></td>'
        .'<td>'.e($row['brand']).' '.e($row['padded_card_number']).'<br><span class="muted">'.sprintf('%02d/%04d', $row['exp_month'], $row['exp_year']).($row['deleted'] ? ' · deleted' : '').'</span></td>'
        .'<td>'.dashboard_button('/dashboard/tokens/'.$row['id'].'/fail-next', $row['fail_next_charge'] ? 'Next charge fails (undo)' : 'Fail next charge')
        .' '.dashboard_button('/dashboard/tokens/'.$row['id'].'/expire', 'Expire card').'</td></tr>', $tokens));

    $deliveryRows = implode('', array_map(fn (array $row): string => '<tr><td class="muted">'.e($row['created']).'</td><td>'.e($row['url']).'</td><td>'.e($row['status'] ?? 'no answer').'</td>'
        .'<td><code>'.e($row['body']).'</code></td><td>'.dashboard_button('/dashboard/deliveries/'.$row['id'].'/resend', 'Resend').'</td></tr>', $deliveries));

    $baseUrl = base_url();
    $resetButton = dashboard_button('/dashboard/reset', 'Delete all data');

    respond_html(layout('Dashboard', <<<HTML
        <div class="card">
            <h1>BML Connect Faker</h1>
            <div class="muted">API base <code>{$baseUrl}</code> · not affiliated with Bank of Maldives</div>
            <div class="actions">{$resetButton}</div>
        </div>
        <div class="card"><h2>Transactions</h2><table><tr><th>Id</th><th>Amount</th><th>State</th><th>localId</th><th>Card</th><th>Updated</th></tr>{$transactionRows}</table></div>
        <div class="card"><h2>Saved cards</h2><table><tr><th>Token</th><th>Customer</th><th>Card</th><th></th></tr>{$tokenRows}</table></div>
        <div class="card"><h2>Webhooks sent</h2><table><tr><th>When</th><th>To</th><th>Status</th><th>Body</th><th></th></tr>{$deliveryRows}</table></div>
        HTML));
}

function dashboard_button(string $action, string $label): string
{
    return '<form class="inline" method="post" action="'.e($action).'"><button>'.e($label).'</button></form>';
}

function dashboard_toggle_fail_next(string $tokenId): never
{
    query('update tokens set fail_next_charge = 1 - fail_next_charge where id = ?', [$tokenId]);
    redirect('/');
}

function dashboard_expire_card(string $tokenId): never
{
    $lastMonth = strtotime('first day of last month');
    query('update tokens set exp_month = ?, exp_year = ? where id = ?', [(int) gmdate('n', $lastMonth), (int) gmdate('Y', $lastMonth), $tokenId]);
    redirect('/');
}

function dashboard_resend(string $deliveryId): never
{
    $delivery = query('select * from deliveries where id = ?', [(int) $deliveryId])->fetch();

    if ($delivery !== false) {
        deliver($delivery['url'], $delivery['body']);
    }

    redirect('/');
}

function dashboard_reset(): never
{
    foreach (['deliveries', 'tokens', 'transactions', 'customers', 'webhooks'] as $table) {
        db()->exec("delete from {$table}");
    }

    redirect('/');
}
