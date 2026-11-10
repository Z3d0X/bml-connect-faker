// Defaults, each overridable by an environment variable. Follows src/php/config.php.

import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
export const SHARED = join(ROOT, 'shared');

const env = (name) => process.env[name] || null;

export const config = {
    apiKey: env('BML_FAKER_API_KEY') ?? 'test-api-key',
    webhookUrl: env('BML_FAKER_WEBHOOK_URL'),
    database: env('BML_FAKER_DATABASE') ?? join(ROOT, 'storage/bml-connect-faker.sqlite'),
    caFile: env('BML_FAKER_CA_FILE') ?? join(homedir(), 'Library/Application Support/Herd/config/valet/CA/LaravelValetCASelfSigned.pem'),
    transactionLifetimeDays: parseInt(env('BML_FAKER_TRANSACTION_LIFETIME_DAYS') ?? '7', 10),
    host: env('BML_FAKER_HOST') ?? '127.0.0.1',
    port: parseInt(env('BML_FAKER_PORT') ?? '8787', 10),
};
