// Signed webhook delivery. Follows src/php/webhooks.php.

import http from 'node:http';
import https from 'node:https';
import tls from 'node:tls';
import { createHash, randomBytes } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';

import { config } from './config.mjs';
import { query, now } from './bootstrap.mjs';

/** Sends the event to the transaction's own webhook, every registered webhook and the configured one. */
export async function sendWebhook(transaction, payload) {
    const registered = query('select hook_url from webhooks').map((row) => row.hook_url);
    const targets = new Set([transaction.webhook_url, ...registered, config.webhookUrl].filter(Boolean));

    for (const url of targets) {
        await deliver(url, JSON.stringify(payload));
    }
}

/** BML signs the headers only: sha256(nonce + timestamp + apiKey). The body is not covered. */
export function deliver(url, body) {
    const nonce = randomBytes(16).toString('hex');
    const sentAt = String(Math.floor(Date.now() / 1000));

    return new Promise((resolve) => {
        let recorded = false;

        const record = (status, response) => {
            if (recorded) {
                return;
            }

            recorded = true;
            query('insert into deliveries (url, body, status, response, created) values (?, ?, ?, ?, ?)', [
                url, body, status, String(response).slice(0, 2000), now(),
            ]);
            resolve();
        };

        try {
            const target = new URL(url);
            const secure = target.protocol === 'https:';
            const options = {
                method: 'POST',
                timeout: 10_000,
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(body),
                    'X-Originator': 'PomeloPay-Webhooks',
                    'X-Signature-Nonce': nonce,
                    'X-Signature-Timestamp': sentAt,
                    'X-Signature': createHash('sha256').update(nonce + sentAt + config.apiKey).digest('hex'),
                },
            };

            if (secure && existsSync(config.caFile)) {
                options.ca = [...tls.rootCertificates, readFileSync(config.caFile)];
            }

            const outgoing = (secure ? https : http).request(target, options, (response) => {
                const chunks = [];
                response.on('data', (chunk) => chunks.push(chunk));
                response.on('end', () => record(response.statusCode, Buffer.concat(chunks).toString()));
                response.on('error', (error) => record(null, error.message));
            });

            outgoing.on('timeout', () => outgoing.destroy(new Error('Timed out after 10 seconds')));
            outgoing.on('error', (error) => record(null, error.message));
            outgoing.end(body);
        } catch (error) {
            record(null, error.message);
        }
    });
}
