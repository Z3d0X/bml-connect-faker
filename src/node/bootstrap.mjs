// Database and helpers. Follows src/php/bootstrap.php.

import { randomBytes } from 'node:crypto';
import { mkdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

import { SHARED, config } from './config.mjs';

// Test cards on the hosted page, by card number. shared/README.md explains the fields.
export const TEST_CARDS = new Map(JSON.parse(readFileSync(join(SHARED, 'cards.json'), 'utf8')).map((card) => [card.number, card]));

export const PENDING_STATES = ['INITIATED', 'QR_CODE_GENERATED'];

mkdirSync(dirname(config.database), { recursive: true });
export const db = new DatabaseSync(config.database);
db.exec(readFileSync(join(SHARED, 'schema.sql'), 'utf8'));

function bindable(value) {
    if (value === undefined || value === null) {
        return null;
    }

    if (typeof value === 'boolean') {
        return Number(value);
    }

    return typeof value === 'object' ? JSON.stringify(value) : value;
}

export function query(sql, bindings = []) {
    const statement = db.prepare(sql);
    const values = bindings.map(bindable);

    return /^\s*select/i.test(sql) ? statement.all(...values) : statement.run(...values);
}

export function find(table, id) {
    return query(`select * from ${table} where id = ?`, [String(id)])[0] ?? null;
}

/** Ids look like BML's: 24 hex characters. */
export const newId = () => randomBytes(12).toString('hex');

export const timestamp = (date = new Date()) => date.toISOString();

export const now = () => timestamp();

/** A value bound for a text column: scalars become strings, as PDO does. */
export function text(value) {
    if (value === undefined || value === null) {
        return null;
    }

    return typeof value === 'object' ? JSON.stringify(value) : String(value);
}

export class Reply {
    constructor(status, headers = {}, body = '') {
        this.status = status;
        this.headers = headers;
        this.body = body;
    }
}

export const respondJson = (data, status = 200) => new Reply(status, { 'Content-Type': 'application/json' }, JSON.stringify(data, null, 4));

export const respondHtml = (html, status = 200) => new Reply(status, { 'Content-Type': 'text/html; charset=utf-8' }, html);

export const redirect = (url) => new Reply(303, { Location: url });

/** Throws, so it can end a handler from anywhere: `find(...) ?? fail(404, ...)`. */
export function fail(status, message) {
    throw respondJson({ message }, status);
}

export function jsonBody(request) {
    try {
        const decoded = JSON.parse(request.body);

        return typeof decoded === 'object' && decoded !== null ? decoded : {};
    } catch {
        return {};
    }
}

function e(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

/** Fills a template from shared/templates: {{name}} is escaped, {{{name}}} is inserted as it is. */
export function render(template, values = {}) {
    return readFileSync(join(SHARED, `templates/${template}.html`), 'utf8')
        .replace(/\{\{(\{?)(\w+)\}?\}\}/g, (match, raw, name) => (raw === '' ? e(values[name]) : String(values[name] ?? '')));
}

export const paddedCardNumber = (number) => number.slice(0, 6) + '*'.repeat(number.length - 10) + number.slice(-4);
