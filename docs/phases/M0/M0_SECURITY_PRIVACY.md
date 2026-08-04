# M0 Security, Privacy and Compliance Baseline

## 1. Source-license boundary

The Olist source is licensed under CC BY-NC-SA 4.0. ReviewLens therefore MUST:

- attribute Olist, the dataset title, source and license;
- remain non-commercial for every Olist-backed demo/artifact;
- apply the same or a compatible license to any distributed data adaptation;
- state material transformations and avoid claims of Olist endorsement.

The license has no 12-month expiry. It also does not waive privacy, publicity or
third-party provider rules. `docs/DATA_ATTRIBUTION.md` is a release artifact,
not optional prose.

## 2. Exposure boundary

The MVP is a local/private portfolio demo. Raw CSVs, review comments, row-level
warehouse exports, embeddings and Chroma collections remain outside Git and are
not published. Private R2 and Snowflake processing is allowed only after the
source manifest and DLP checks pass. OpenRouter receives only an approved,
minimized review projection; CI and public screenshots use synthetic, aggregate
or redacted evidence.

## 3. Data classification and allowed use

| Data | Class | Snowflake analytics | OpenRouter | ChromaDB | Logs/public evidence |
|---|---|---|---|---|---|
| Order/product/payment values | Internal source data | Private, approved columns | No | Filter metadata only if needed | Aggregate only |
| Customer/seller IDs | Pseudonymous | Hashed/minimized serving layer | No | No raw ID; stable policy ID only | Never raw |
| City/state/ZIP prefix | Quasi-identifier | Coarsened/approved | Only if retrieval needs it | Approved filter metadata | Aggregate; suppress small groups |
| Review score | Internal source data | Yes | Context only when required | Approved filter metadata | Aggregate |
| Review title/comment | Restricted UGC/untrusted | Private; serving-safe projection | Only after DLP/minimization | Redacted serving-safe text only | No raw excerpt by default |
| Query/prompt | Restricted telemetry | No raw mart | Needed for request | No | Hash/redacted summary |
| LLM output | Internal AI artifact | Validated fields only | N/A | Approved summary/chunk only | Aggregate/curated |
| Credentials/tokens | Secret | Never | Auth header only | Service boundary only | Never |

## 4. DLP and AI-transfer gate

Before a real review comment is sent to OpenRouter or embedded:

1. select only review/order evidence needed by the use case;
2. detect and redact emails, phone numbers, URLs, payment-like strings, direct
   identifiers and high-risk free-text patterns;
3. drop unnecessary customer/seller/order identifiers from prompt text;
4. tag `policy_version`, content hash and DLP decision;
5. reject failed/ambiguous rows to quarantine rather than bypass the gate;
6. validate provider/model data policy and budget at runtime.

Prompt injection text is data, never an instruction. Prompts delimit evidence,
disable tools and require structured output.

## 5. Provider and secret rules

- R2 stays private; credentials are bucket-scoped and never exposed to browsers.
- Snowflake service users do not use `ACCOUNTADMIN`; Text-to-SQL disables
  secondary roles and uses an isolated warehouse/read-only role.
- `.env` and private keys remain outside Git; errors/logs redact seeded secrets.
- Chroma writer/reader boundaries and candidate/active collections are separate.
- Service identity rotation/revocation runbooks precede any shared demo.

## 6. Retention baseline

| Artifact | Default | Notes |
|---|---|---|
| Local source CSVs | Owner-controlled, outside Git; review every 90 days | Delete when project ends or risk/terms change |
| R2 `source/` | 90 days | Private; lifecycle enabled; manifest retained longer |
| R2 raw/quarantine | 30 days | Quarantine access restricted |
| Snowflake candidate schemas | 14 days after rejection | Active + one rollback release retained |
| OpenRouter request/response body | Do not persist raw by default | Ledger stores hashes/tokens/model/status |
| AI error payload | 14 days maximum | Redact and restrict |
| Chroma candidate collections | 7 days after rejection | Never delete active collection implicitly |
| App/query audit | 30 days local | Avoid raw questions when possible |

## 7. Threat priorities

| Threat | Mandatory control |
|---|---|
| Prompt injection in reviews | Delimit untrusted content, no tools, structured schema, adversarial corpus |
| SQL write/exfiltration/cost abuse | AST allowlist, read-only role, timeout, row cap, isolated warehouse |
| Candidate or cross-release leakage | Pinned physical refs, active pointer, negative tests |
| Raw-data/Git leak | `.gitignore`, tracked/untracked scans, synthetic public evidence |
| Secret leak | `.env` boundary, secret scan, sanitized provider errors |
| Public R2 exposure | Disabled public access and anonymous-denial probe |
| License breach | Attribution/non-commercial/ShareAlike release check |
| Restore deleted/restricted data | Tombstone/denylist reapplication during rebuild |
