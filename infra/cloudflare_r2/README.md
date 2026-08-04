# Cloudflare R2 contract

The local portfolio runtime uses the existing private Standard bucket `reviewlens-data-dev` with the versioned prefixes from `config/config.toml`.

The application token must use **Object Read & Write** scoped only to this bucket. It must not have account-level bucket administration. Bucket lifecycle changes require a separate owner/admin action and are intentionally not performed with the application credential.

`lifecycle.json` expires abandoned synthetic smoke-test objects under `manifests/_smoke/` after one day and keeps the seven-day incomplete multipart cleanup baseline. Review the current bucket rules before applying because setting a lifecycle configuration replaces the existing configuration.

Example owner-operated command after review:

```powershell
npx wrangler r2 bucket lifecycle set reviewlens-data-dev --file infra/cloudflare_r2/lifecycle.json
```

The live test deletes its object in a `finally` block; the lifecycle rule is defense in depth, not the primary cleanup mechanism.

Reference: [Cloudflare R2 object lifecycle documentation](https://developers.cloudflare.com/r2/buckets/object-lifecycles/).
