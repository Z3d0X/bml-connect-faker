<?php

declare(strict_types=1);

/**
 * Sends a template from shared/templates inside the layout.
 */
function page(string $title, string $template, array $values = [], int $status = 200): never
{
    respond_html(render('layout', ['title' => $title, 'body' => render($template, $values)]), $status);
}

function formatted_amount(array $transaction): string
{
    return number_format($transaction['amount'] / 100, 2);
}

function result_page(array $transaction): never
{
    page('Payment', 'result', [...$transaction, 'amount' => formatted_amount($transaction)]);
}

function page_pay(string $id): never
{
    $transaction = find('transactions', $id) ?? page('Not found', 'message', ['message' => 'No such transaction.'], 404);

    if (! is_payable($transaction)) {
        result_page($transaction);
    }

    $options = '';

    foreach (array_values(TEST_CARDS) as $index => $card) {
        $options .= render('pay-option', [
            ...$card,
            'spaced_number' => trim(chunk_split($card['number'], 4, ' ')),
            'checked' => $index === 0 ? 'checked' : '',
        ]);
    }

    page('Payment', 'pay', [
        ...$transaction,
        'amount' => formatted_amount($transaction),
        'options' => $options,
        'saving_hidden' => $transaction['tokenize'] ? '' : 'hidden',
    ]);
}

function page_pay_submit(string $id): never
{
    $transaction = find('transactions', $id) ?? page('Not found', 'message', ['message' => 'No such transaction.'], 404);

    if (! is_payable($transaction)) {
        result_page($transaction);
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
        page('3D Secure', '3ds', ['card' => $cardNumber]);
    }

    finish(pay_on_hosted_page($transaction, $cardNumber));
}

function finish(array $transaction): never
{
    if ($transaction['redirect_url'] !== null && $transaction['redirect_url'] !== '') {
        redirect(redirect_back_url($transaction));
    }

    result_page($transaction);
}

function page_short_link(string $code): never
{
    $transaction = query('select id from transactions where short_code = ?', [$code])->fetch();

    $transaction === false ? page('Not found', 'message', ['message' => 'No such link.'], 404) : redirect('/pay/'.$transaction['id']);
}

function page_dashboard(): never
{
    $transactions = query('select * from transactions order by created desc limit 50')->fetchAll();
    $tokens = query('select tokens.*, customers.name, customers.email from tokens join customers on customers.id = tokens.customer_id order by tokens.created desc limit 50')->fetchAll();
    $deliveries = query('select * from deliveries order by id desc limit 30')->fetchAll();

    page('Dashboard', 'dashboard', [
        'base_url' => base_url(),
        'transactions' => implode('', array_map(fn (array $row): string => render('dashboard-transaction', [
            ...$row,
            'amount' => formatted_amount($row),
            'card' => $row['tokenize'] ? 'saves card' : ($row['token_id'] ? 'saved card' : ''),
        ]), $transactions)),
        'tokens' => implode('', array_map(fn (array $row): string => render('dashboard-token', [
            ...$row,
            'expiry' => sprintf('%02d/%04d', $row['exp_month'], $row['exp_year']),
            'deleted_hidden' => $row['deleted'] ? '' : 'hidden',
            'fail_next_label' => $row['fail_next_charge'] ? 'Next charge fails (undo)' : 'Fail next charge',
        ]), $tokens)),
        'deliveries' => implode('', array_map(fn (array $row): string => render('dashboard-delivery', [
            ...$row,
            'status' => $row['status'] ?? 'no answer',
        ]), $deliveries)),
    ]);
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
