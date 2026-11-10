create table if not exists customers (
    id text primary key,
    name text not null,
    email text not null,
    payload text not null,
    created text not null
);

create table if not exists transactions (
    id text primary key,
    short_code text not null unique,
    amount integer not null,
    currency text not null,
    state text not null,
    customer_id text,
    local_id text,
    customer_reference text,
    redirect_url text,
    webhook_url text,
    provider text,
    tokenize integer not null default 0,
    payment_type text,
    recurring_frequency text,
    token_id text,
    padded_card_number text,
    card_exp_month integer,
    card_exp_year integer,
    expires text not null,
    created text not null,
    updated text not null
);

create table if not exists tokens (
    id text primary key,
    customer_id text not null,
    card_number text not null,
    brand text not null,
    padded_card_number text not null,
    exp_month integer not null,
    exp_year integer not null,
    agreement_type text,
    fail_next_charge integer not null default 0,
    deleted integer not null default 0,
    created text not null
);

create table if not exists webhooks (
    id text primary key,
    hook_url text not null,
    created text not null
);

create table if not exists deliveries (
    id integer primary key autoincrement,
    url text not null,
    body text not null,
    status integer,
    response text,
    created text not null
);
