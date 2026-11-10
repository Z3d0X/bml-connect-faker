#!/usr/bin/env node

/*
 * BML Connect Faker in Node. Needs Node 22.13+ and nothing else.
 *
 *     node src/node/server.mjs
 *
 * The files in this folder follow the PHP ones of the same name, function by function: this one is
 * src/php/server.php. A change to one implementation belongs in all of them; tests/conformance.py checks
 * that they agree. The schema, the test cards and the HTML are in shared/, read by every implementation.
 */

import http from 'node:http';

import { config } from './config.mjs';
import { Reply, respondJson, fail } from './bootstrap.mjs';
import {
    authenticate, apiCreateCustomer, apiCreateTransaction, apiGetTransaction, apiCancelTransaction, apiListTokens,
    apiDeleteToken, apiChargeToken, apiRegisterWebhook,
} from './api.mjs';
import {
    pagePay, pagePaySubmit, pageShortLink, pageDashboard, dashboardToggleFailNext, dashboardExpireCard,
    dashboardResend, dashboardReset,
} from './pages.mjs';

// [method, path pattern, handler, needs the API key]
const ROUTES = [
    ['POST', /^\/public-customers$/, apiCreateCustomer, true],
    ['POST', /^\/public-customers\/charge$/, apiChargeToken, true],
    ['GET', /^\/public-customers\/([^/]+)\/tokens$/, apiListTokens, true],
    ['DELETE', /^\/public-customers\/([^/]+)\/tokens\/([^/]+)$/, apiDeleteToken, true],
    ['POST', /^\/public\/v2\/transactions$/, apiCreateTransaction, true],
    ['GET', /^\/public\/v2\/transactions\/([^/]+)$/, apiGetTransaction, true],
    ['POST', /^\/public\/transactions\/([^/]+)\/cancel$/, apiCancelTransaction, true],
    ['POST', /^\/public\/webhooks$/, apiRegisterWebhook, true],

    ['GET', /^\/pay\/([^/]+)$/, pagePay, false],
    ['POST', /^\/pay\/([^/]+)$/, pagePaySubmit, false],
    ['GET', /^\/p\/([^/]+)$/, pageShortLink, false],

    ['GET', /^\/$/, pageDashboard, false],
    ['POST', /^\/dashboard\/tokens\/([^/]+)\/fail-next$/, dashboardToggleFailNext, false],
    ['POST', /^\/dashboard\/tokens\/([^/]+)\/expire$/, dashboardExpireCard, false],
    ['POST', /^\/dashboard\/deliveries\/([0-9]+)\/resend$/, dashboardResend, false],
    ['POST', /^\/dashboard\/reset$/, dashboardReset, false],
];

async function handle(request) {
    const path = request.url.split('?')[0].replace(/\/+$/, '') || '/';

    for (const [method, pattern, handler, needsApiKey] of ROUTES) {
        const matches = method === request.method ? pattern.exec(path) : null;

        if (matches !== null) {
            if (needsApiKey) {
                authenticate(request);
            }

            return handler(request, ...matches.slice(1));
        }
    }

    fail(404, `No route for ${request.method} ${path}`);
}

const server = http.createServer(async (incoming, outgoing) => {
    const chunks = [];

    for await (const chunk of incoming) {
        chunks.push(chunk);
    }

    const request = {
        method: incoming.method,
        url: incoming.url,
        headers: incoming.headers,
        body: Buffer.concat(chunks).toString(),
        baseUrl: `${incoming.headers['x-forwarded-proto'] === 'https' ? 'https' : 'http'}://${incoming.headers.host ?? 'localhost'}`,
    };

    let reply;

    try {
        reply = await handle(request);
    } catch (thrown) {
        if (thrown instanceof Reply) {
            reply = thrown;
        } else {
            console.error(thrown);
            reply = respondJson({ message: `Faker error: ${thrown.message}` }, 500);
        }
    }

    console.log(`${request.method} ${request.url} ${reply.status}`);
    outgoing.writeHead(reply.status, reply.headers).end(reply.body);
});

server.listen(config.port, config.host, () => {
    console.log(`BML Connect Faker (Node) listening on http://${config.host}:${config.port}`);
});
