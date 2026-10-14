# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| `main` (latest commit) | ✅ |
| Older commits, forks, tags | ❌ |

This is a demo / portfolio project. Security fixes land on `main` only.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report vulnerabilities privately through GitHub's **private vulnerability reporting**:
open the repository's **Security** tab → **Report a vulnerability**. Include:

- the affected endpoint, file or configuration,
- reproduction steps or a proof of concept,
- the impact you observed (data exposure, cost abuse, privilege escalation, …).

You should get an acknowledgement within a few days. Please give a reasonable
window to fix the issue before any public disclosure.

## Security model (summary)

The app uses a **hybrid exposure** model, enforced by the FastAPI backend with
**default deny** (see [README › Security model](README.md#-security-model) for
details):

- **Anonymous** callers may load the SPA, call `GET /api/health`, `GET /api/me`,
  `GET /api/avatars`, list and play **published** UC2 videos / UC3 podcasts and
  view **published** UC1 decks (slide images + titles only — no speaker notes,
  body text or PPTX download).
- **Admins** — callers signed in with **Microsoft Entra ID** through Azure
  Container Apps built-in authentication (**Easy Auth**) whose object ID is in
  `ALLOWED_OBJECT_IDS` — can do everything else (uploads, live avatar, renders,
  translation, agent chat, publish/unpublish, deletes, unpublished items).
- Gated endpoints answer **401** (anonymous) or **403** (signed in but not
  allowlisted). The live-avatar WebSocket (`/ws/voice`) is authorized and its
  `Origin` checked **before** the connection is accepted.
- Identity headers (`X-MS-CLIENT-PRINCIPAL*`) are trusted only when
  `AUTH_MODE=easyauth`; Azure Container Apps strips client-supplied copies.
  The tenant (`AUTH_TENANT_ID`) and identity provider (`aad`) are verified.
- Generated content is **unpublished by default**. Anonymous media links are
  read-only, blob-scoped SAS URLs that expire after 15 minutes.
- Azure services are reached with a **managed identity** (`DefaultAzureCredential`);
  Speech credentials are never sent to the browser.
- Cost / abuse guards: `MAX_VOICE_SESSIONS`, `MAX_VOICE_SESSION_SECONDS`,
  `DAILY_GENERATION_QUOTA`, `MAX_PENDING_RENDERS`, plus an Azure budget alert.
- `AUTH_MODE=disabled` exists **for local development only**: every caller is
  treated as admin and the backend logs a warning at startup.

## Operator checklist

Before (and after) every deployment of your own instance:

- [ ] **Entra app registration** — create a dedicated app registration for sign-in
      (web redirect URI `https://<your-app-fqdn>/.auth/login/aad/callback`, ID
      tokens enabled) and a client secret; set `AUTH_CLIENT_ID` and
      `AUTH_CLIENT_SECRET` in the `azd` environment. Rotate the secret before it
      expires and never commit it.
- [ ] **Allowlist** — set `ALLOWED_OBJECT_IDS` to the Entra object IDs of the
      people who may administer the app (keep it short). An empty list means
      nobody is admin. The `azd` preprovision hook refuses to deploy without
      `AUTH_CLIENT_ID`, `AUTH_CLIENT_SECRET` and `ALLOWED_OBJECT_IDS`.
- [ ] **Keep `AUTH_MODE=easyauth` in Azure** — never deploy with
      `AUTH_MODE=disabled`, and never expose a local `AUTH_MODE=disabled`
      instance to a network.
- [ ] **Budget alert** — set `BUDGET_CONTACT_EMAILS` (and `BUDGET_AMOUNT`) in the
      `azd` environment; no budget is deployed without recipients. Confirm the
      monthly alert on the resource group has the right amount and recipients. Live avatar streaming and batch
      avatar synthesis are billed per minute of video.
- [ ] **Limits** — review `MAX_VOICE_SESSIONS`, `MAX_VOICE_SESSION_SECONDS`,
      `DAILY_GENERATION_QUOTA` and `MAX_PENDING_RENDERS` for your expected usage.
- [ ] **Origins & framing** — only add trusted origins to `ALLOWED_ORIGINS`;
      keep `FRAME_ANCESTORS` limited to the hosts that embed the app (Teams /
      Office by default).
- [ ] **Publishing** — review what is published; anything published is
      visible to anyone with the URL.
- [ ] **Custom avatars** — keep avatar photos out of git
      (`demos/backend/static/avatars/` is ignored) and only use likenesses you
      have consent for.
- [ ] **URL ingestion** — leave `ENABLE_URL_INGEST=false` unless you need it.
