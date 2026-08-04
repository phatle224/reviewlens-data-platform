# User Inputs Before M1 Live Setup

Do not paste passwords, API keys, access keys, secret keys or private-key
contents into chat or repository files. Secrets live only in the ignored local
`.env` or an outside-repository key path.

| ID | Status | Confirmed value |
|---|---|---|
| UI-01 | `RESOLVED` | Personal, non-commercial student learning/portfolio project; local demo with video/screenshots, no public live URL |
| UI-02 | `RESOLVED` | Snowflake Standard Edition on AWS Singapore (`AWS_AP_SOUTHEAST_1`); trial expires `2026-09-03`; displayed balance `US$400` on 2026-08-04 |
| UI-03 | `RESOLVED` | Private R2 bucket `reviewlens-data-dev`, APAC location hint, Standard storage, public access disabled, lifecycle applied |
| UI-04 | `RESOLVED` | OpenRouter hard project budget 5 USD; current evaluation model set accepted provisionally |
| UI-05 | `RESOLVED` | Olist Brazilian E-Commerce dataset selected as the only active real source; nine CSVs downloaded locally on 2026-08-05 |
| UI-06 | `RESOLVED` | Source license CC BY-NC-SA 4.0; project accepts attribution, NonCommercial, ShareAlike and change-indication obligations |
| UI-07 | `RESOLVED` | Source code may be public; raw CSVs, review text, row-level exports, embeddings and vector data may not be committed or published |

## Topology interpretation

- Snowflake running on AWS does not require AWS S3. It accesses private R2 via
  the S3-compatible HTTPS endpoint and `s3compat://` stage protocol.
- R2 SDK region is `auto`; `AWS_AP_SOUTHEAST_1` applies only to Snowflake.
- The local source snapshot is metadata-profiled in
  `docs/data/OLIST_SOURCE_MANIFEST.md`; M2 performs the explicit R2 upload.
- `data_mode` remains `synthetic` during M1 foundation tests. Switching to
  `olist` is an M2 operator action after manifest/privacy gates.
