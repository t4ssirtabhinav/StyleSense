# infra/

Out-of-band infrastructure configuration that lives outside any deployable
artifact — settings applied to an external provider's control plane rather
than shipped as code.

## `r2-cors.json` — Cloudflare R2 bucket CORS policy

Required for **browser-based** uploads. The mobile client (web) PUTs directly
to a presigned R2 URL from the browser (`wardrobe.service.ts`'s
`uploadToR2WithProgress`), so R2 must answer the browser's CORS preflight.
Without this policy R2 returns `403` to the preflight `OPTIONS` with no
`Access-Control-Allow-Origin` header, and the upload never starts. Native
(iOS/Android) is unaffected — CORS is a browser concept — which is why this
gap survived from SS-010 until the first real browser upload in SS-014.

Applied via the S3-compatible `PutBucketCors` API using the existing
`CLOUDFLARE_R2_*` credentials ([VERIFIED 2026-07-27,
developers.cloudflare.com/r2/api/s3/api/ — `PutBucketCors`/`GetBucketCors`
are both listed as implemented]). No Cloudflare account API token is needed,
only the R2 access keys already in `.env`.

To re-apply after editing:

```bash
node infra/apply-r2-cors.mjs
```

**`AllowedOrigins: ["*"]` is deliberate for now, and should be tightened
before public launch** (tracked as `BL-070`). Rationale: the presigned URL —
short-lived (300s) and issued only by the JWT-authed `get-upload-url` Edge
Function — is the actual security boundary here, not the CORS origin list. A
third-party page cannot obtain a presigned URL without the user's session. A
strict allowlist is also impractical during development, where the origin is
variously `localhost:8081`, a LAN IP, and a per-session-random `--tunnel`
subdomain.
