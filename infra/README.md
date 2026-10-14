# Infrastructure (azd + Bicep)

`azd up` provisions everything into `rg-<AZURE_ENV_NAME>`:

| Resource | Notes |
|---|---|
| User-assigned managed identity `id-*` | Created first; used for ACR pull and every data-plane call (`AZURE_CLIENT_ID`). |
| Container Registry `cr*` | Admin user disabled; the identity has `AcrPull`. |
| Container Apps environment + app `ca-*` | Scale 0–1 replicas, Easy Auth (Microsoft Entra ID) in hybrid mode. |
| Azure OpenAI `oai-*` | Local (key) auth disabled. |
| Azure AI Services `ais-*` (Speech/Avatar) | Skipped when an external resource is used. Local auth disabled. |
| Cosmos DB (serverless) | Local (key) auth disabled; RBAC data contributor for the identity. |
| Storage account | Shared-key access disabled; SAS URLs are signed with a user delegation key. |
| Log Analytics workspace | Container Apps logs (key never emitted as an output). |
| Budget (optional) | Monthly, alerts at 80 % actual and 100 % forecasted. |

## Authentication (fail closed)

A `preprovision` hook (`hooks/preprovision.ps1` / `hooks/preprovision.sh`) aborts
`azd provision` / `azd up` unless these azd env values are set:

```bash
azd env set AUTH_CLIENT_ID <entra-app-client-id>
azd env set AUTH_CLIENT_SECRET <entra-app-client-secret>   # stored as a Container App secret
azd env set ALLOWED_OBJECT_IDS <oid1>,<oid2>                # admins (Entra object IDs)
azd env set AUTH_TENANT_ID <tenant-guid>                    # optional, defaults to the subscription tenant
```

The app registration needs the redirect URI
`https://<app-fqdn>/.auth/login/aad/callback` and ID-token issuance.
Easy Auth runs with `unauthenticatedClientAction: AllowAnonymous`: anonymous
visitors reach the SPA and the published library; the backend authorizes every
other route from the platform-injected principal headers and `ALLOWED_OBJECT_IDS`.

For a throw-away, public, read-only demo only, `azd env set ALLOW_INSECURE_NO_AUTH true`
skips the check (loud warning). Easy Auth is then not configured and the admin
allowlist is forced empty, so nobody can act as admin.

## Optional settings (azd env)

| Variable | Default | Purpose |
|---|---|---|
| `ALLOWED_ORIGINS` | empty | Extra CORS / WebSocket origins (comma-separated); same-origin is always allowed. |
| `AUTH_EXTRA_CLIENT_APPS` | empty | Extra client application IDs allowed to call the app with bearer tokens (e.g. Azure CLI `04b07795-8ddb-461a-bbee-02f9e1bf7b46` for scripted tests, which also needs pre-authorization on the app registration). Empty = only the app itself. |
| `CUSTOM_AVATARS_JSON` | empty | JSON array of custom photo avatars. Thumbnails must exist in `demos/backend/static/avatars/` at build time. |
| `ENABLE_URL_INGEST` | `false` | Allow podcast URL ingestion. |
| `MAX_VOICE_SESSIONS` / `MAX_VOICE_SESSION_SECONDS` | `2` / `900` | Live avatar limits. |
| `DAILY_GENERATION_QUOTA` / `MAX_PENDING_RENDERS` | `50` / `3` | Cost guardrails. |
| `USE_EXTERNAL_AI_SERVICES` | `false` | Reuse an existing AI Services / Speech resource (e.g. one hosting custom photo avatars). |
| `EXTERNAL_AI_SERVICES_ENDPOINT` / `_REGION` / `_RESOURCE_ID` | empty | Details of that resource (may be in another resource group of the same subscription). |
| `ASSIGN_EXTERNAL_AI_SERVICES_ROLES` | `true` | Grant the app identity `Cognitive Services User`, `Cognitive Services Speech User` and `Foundry User` on the external resource. Requires Owner / User Access Administrator on its resource group; set `false` and assign them manually otherwise. |
| `EXTRA_TAGS_JSON` | empty | JSON object merged into every resource's tags, e.g. `{"CostCenter":"demo"}`. Use it for tags required or exempted by policy on policy-managed enterprise subscriptions. |
| `BUDGET_CONTACT_EMAILS` | empty | Comma-separated recipients; the budget is deployed only when set. |
| `BUDGET_AMOUNT` | `50` | Monthly amount in the billing currency. |
| `BUDGET_START_DATE` | current month | `yyyy-MM-01`; pin it to the creation month if a later re-provision rejects a changed start date. |

Values are strings in the azd environment; JSON values must be valid JSON
(quote them for your shell), e.g. on PowerShell:
`azd env set EXTRA_TAGS_JSON '{\"CostCenter\":\"demo\"}'`.

> **JSON values must be escaped.** azd substitutes env values verbatim into `main.parameters.json`, so every `"` inside `EXTRA_TAGS_JSON` / `CUSTOM_AVATARS_JSON` must be written as `\"` (backslash-quote), as in the examples, or provisioning fails with *invalid character after object key:value pair*.

## Not provisioned

Azure AI Search is not part of this template (`USE_LOCAL_SEARCH=true`). If you
add one, disable its local auth and grant the identity `Search Index Data
Contributor` and `Search Service Contributor` instead of using an admin key.
