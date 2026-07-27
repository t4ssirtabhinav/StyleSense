// Applies infra/r2-cors.json to the Cloudflare R2 bucket via the
// S3-compatible PutBucketCors API, then reads it back to confirm.
//
// Why this exists: browser uploads PUT directly to a presigned R2 URL, so R2
// itself must answer the browser's CORS preflight. See infra/README.md.
//
// Run: node infra/apply-r2-cors.mjs
// Requires CLOUDFLARE_R2_* in the repo-root .env (never printed by this
// script -- only key names and the resulting policy are logged).

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  GetBucketCorsCommand,
  PutBucketCorsCommand,
  S3Client,
} from '@aws-sdk/client-s3';

// STYLESENSE_ROOT lets this run from a scratch directory that has the AWS
// SDK installed, without adding it as a repo dependency just for a one-off
// infra command (ESM ignores NODE_PATH, so the script has to live next to
// its node_modules).
const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = process.env.STYLESENSE_ROOT ?? join(here, '..');
const policyDir = process.env.STYLESENSE_ROOT ? join(repoRoot, 'infra') : here;

function loadEnv() {
  const raw = readFileSync(join(repoRoot, '.env'), 'utf8');
  const env = {};
  for (const line of raw.split(/\r?\n/)) {
    const match = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
    if (match) env[match[1]] = match[2].replace(/^["']|["']$/g, '');
  }
  return env;
}

const env = loadEnv();
const required = [
  'CLOUDFLARE_R2_ACCOUNT_ID',
  'CLOUDFLARE_R2_ACCESS_KEY',
  'CLOUDFLARE_R2_SECRET_KEY',
  'CLOUDFLARE_R2_BUCKET',
];
const missing = required.filter((k) => !env[k]);
if (missing.length > 0) {
  console.error(`Missing in .env: ${missing.join(', ')}`);
  process.exit(1);
}

const bucket = env.CLOUDFLARE_R2_BUCKET;
const corsRules = JSON.parse(
  readFileSync(join(policyDir, 'r2-cors.json'), 'utf8'),
);

const s3 = new S3Client({
  region: 'auto',
  endpoint: `https://${env.CLOUDFLARE_R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: env.CLOUDFLARE_R2_ACCESS_KEY,
    secretAccessKey: env.CLOUDFLARE_R2_SECRET_KEY,
  },
});

await s3.send(
  new PutBucketCorsCommand({
    Bucket: bucket,
    CORSConfiguration: { CORSRules: corsRules },
  }),
);
console.log(`PutBucketCors OK on bucket "${bucket}"`);

const readBack = await s3.send(new GetBucketCorsCommand({ Bucket: bucket }));
console.log('GetBucketCors read-back:');
console.log(JSON.stringify(readBack.CORSRules, null, 2));
