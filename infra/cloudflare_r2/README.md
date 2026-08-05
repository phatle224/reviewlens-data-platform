# Cloudflare R2 contract

The local portfolio runtime uses the existing private Standard bucket `reviewlens-data-dev` with the versioned prefixes from `config/config.toml`.

Runtime uses two bucket-scoped tokens: ingestion has **Object Read & Write** and
the Snowflake stage has **Object Read only**. Neither token has account-level
bucket administration. The older `R2_*` credential remains bootstrap/live-smoke
only. Bucket lifecycle changes require a separate owner/admin action and are
intentionally not performed with either runtime credential.

`lifecycle.json` expires abandoned synthetic smoke-test objects under `manifests/_smoke/` after one day and keeps the seven-day incomplete multipart cleanup baseline. Review the current bucket rules before applying because setting a lifecycle configuration replaces the existing configuration.

Example owner-operated command after review:

```powershell
npx wrangler r2 bucket lifecycle set reviewlens-data-dev --file infra/cloudflare_r2/lifecycle.json
```

The live test deletes its object in a `finally` block; the lifecycle rule is defense in depth, not the primary cleanup mechanism.

Run the dedicated runtime-identity test:

```powershell
$env:REVIEWLENS_RUN_LIVE_R2_IDENTITIES='1'
.venv\Scripts\pytest.exe tests\live\test_r2_identities_live.py -q -rs -p no:cacheprovider
```

It proves ingestion can write/read/delete a synthetic smoke object, the stage
identity can read/list it, both identities cannot list account buckets, and a
direct stage write is denied by Cloudflare. Cleanup uses the ingestion identity.

Reference: [Cloudflare R2 object lifecycle documentation](https://developers.cloudflare.com/r2/buckets/object-lifecycles/).
