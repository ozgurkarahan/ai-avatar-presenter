# BOOTSTRAP: deploying Oz Radio (instructions for coding agents)

> These are instructions for an AI coding agent deploying Oz Radio to Azure.
> The full runbook is [`docs/provisioning.md`](docs/provisioning.md); each step below
> references its sections. Run the steps **in order**. Don't skip a gate.
> The steps are documented from the repo and must be validated on a fresh environment;
> report any mismatch to the human.

## Rules (non-negotiable)

1. **Secrets:** never print, log, echo, commit or paste secrets. That includes client secrets, tokens and keys.
   - Pipe secrets directly into `azd env set`.
   - Never `cat` or `type` `.azure/<env>/.env`.
   - Don't add secrets, tenant/subscription/object IDs, customer names or personal IPs to tracked files.
2. **Auth:** never set `AUTH_MODE=disabled` in Azure. Don't use `ALLOW_INSECURE_NO_AUTH=true` unless the human explicitly asks for a throw-away read-only demo.
3. **Never weaken security to get green.** Don't touch these:
   - auth or Easy Auth settings;
   - `disableLocalAuth`, `allowSharedKeyAccess` or `adminUserEnabled`;
   - role scopes;
   - ICE `iceTransportPolicy: 'relay'`;
   - origin checks, quotas or demo caps.

   If a gate fails because of them, **stop and report**.
4. **No new scripts.** Use the commands shown in `docs/provisioning.md`. Don't add script files to the repo.
5. **Verify each gate before you continue.** If a command fails, diagnose it with [§9](docs/provisioning.md#9-troubleshooting). Don't retry blindly. Don't edit Bicep without asking.
6. **Definition of done:** the deployment is done only when every item in the
   [smoke-test checklist (§7)](docs/provisioning.md#7-smoke-test-checklist) passes **in a real browser**.
   That means sign-in, a slide upload that renders, and an avatar with **video and audio**. HTTP 200s alone don't count.

## 🛑 STOP AND ASK THE HUMAN when you need to…

- [ ] Choose the **tenant and subscription**. Never guess from `az account list`.
- [ ] Choose the **region**. Default suggestion: `swedencentral` (tested). Check it against [§2.4](docs/provisioning.md#24-region).
- [ ] Decide on an **external AI Services** resource (`USE_EXTERNAL_AI_SERVICES`) and its details.
- [ ] Decide on **custom photo avatars** (`CUSTOM_AVATARS_JSON`, `HIDE_STOCK_AVATARS`). They need the thumbnails copied into
      `demos/backend/static/avatars/` (git-ignored) and the Speech resource that hosts them ([§4.1](docs/provisioning.md#41-custom-photo-avatars-optional)).
- [ ] **Create the Entra app registration and client secret**, or get approval to create them ([§3](docs/provisioning.md#3-entra-app-registration-easy-auth)).
- [ ] Get **`ALLOWED_OBJECT_IDS`**: who may be admin. Get object IDs, not e-mails.
- [ ] Get **budget recipients and amount** (`BUDGET_CONTACT_EMAILS`, `BUDGET_AMOUNT`).
- [ ] Get **required tags** for policy (`EXTRA_TAGS_JSON`).
- [ ] **Enable the public demo** (`PUBLIC_DEMO_ENABLED`) or mark decks *Live demo*. This exposes paid avatar minutes to anonymous visitors.
- [ ] **Enable voice Q&A in the public demo** (`DEMO_QA_ENABLED`). Only after the smoke test passes; it adds paid speech-to-text and `gpt-4.1` calls ([§6.3](docs/provisioning.md#63-voice-qa-in-the-public-demo-demo_qa_enabled)).
- [ ] **Seed content**: upload and publish the AI enablement series ([§6.1](docs/provisioning.md#61-first-use)).
- [ ] Handle any **quota request, policy exemption, provider registration or role assignment** you lack rights for.
- [ ] Decide what to do about anything that would require editing `infra/` or weakening a setting.
- [ ] Run `azd down` / teardown.

## Steps

1. **Read** [`docs/provisioning.md`](docs/provisioning.md) §1–§5, `azure.yaml`, `infra/main.parameters.json` and `hooks/preprovision.*`.
2. **Tools gate ([§2.1](docs/provisioning.md#21-tools)).** `azd version`, `az version`, and `pwsh -v` on Windows. Docker isn't needed.
3. **Identity gate.** 🛑 Confirm the tenant and subscription with the human. Then:
   1. Run `az login`, `azd auth login` and `az account set -s <subscription-id>`.
   2. Run `az account show --query "{name:name, tenant:tenantId}"` and confirm the result with the human.
4. **Permissions gate ([§2.2](docs/provisioning.md#22-permissions)).** Confirm you have Contributor and a role-assignment role (Owner, User Access Administrator or RBAC Administrator) at subscription scope:
   ```bash
   az role assignment list --assignee <your-oid> --scope /subscriptions/<subscription-id> -o table
   ```
5. **Providers gate ([§2.3](docs/provisioning.md#23-resource-providers)).** Every listed provider is `Registered`. Ask before you register any.
6. **Region and quota gate ([§2.4](docs/provisioning.md#24-region), [§2.5](docs/provisioning.md#25-quota)).** 🛑 Confirm the region. Then confirm:
   - `gpt-4.1` (2025-04-14) and `text-embedding-3-small` (1) are GlobalStandard in that region;
   - free quota is at least 80 for `gpt-4.1` and at least 120 for `text-embedding-3-small`;
   - the Learn region tables list real-time avatar, batch avatar and Voice Live there.
7. **Policy gate ([§2.6](docs/provisioning.md#26-azure-policy-pitfalls-enterprise--policy-managed-subscriptions)).** List policy assignments. Report any that require tags, deny public network access, restrict SKUs or locations, or deny role assignments.
8. **Environment.** Run `azd env new <env-name>`, then set `AZURE_LOCATION` and `AZURE_SUBSCRIPTION_ID`.
9. **Entra gate ([§3](docs/provisioning.md#3-entra-app-registration-easy-auth)).** 🛑 Ask the human for approval, or for the values.
   1. Set `AUTH_CLIENT_ID`, `AUTH_CLIENT_SECRET` (piped, never printed), `ALLOWED_OBJECT_IDS` and optionally `AUTH_TENANT_ID`.
   2. Confirm each value is set **without printing the secret**:
      ```bash
      azd env get-value AUTH_CLIENT_ID
      azd env get-value ALLOWED_OBJECT_IDS
      azd env get-values | grep -c '^AUTH_CLIENT_SECRET='   # prints 1; on PowerShell use: (azd env get-values | Select-String '^AUTH_CLIENT_SECRET=').Count
      ```
10. **Optional settings ([§4](docs/provisioning.md#4-azd-environment-variables)).** 🛑 Get the budget, tags and avatar choices from the human. Escape JSON values with `\"`.
11. **Provision.** Run `azd provision`.
    - Gate: the hook prints `preprovision: Easy Auth configuration present` and the deployment succeeds.
    - Gate: `azd env get-value AZURE_CONTAINER_APP_URL` returns a URL.
12. **Redirect URI.** Add `<AZURE_CONTAINER_APP_URL>/.auth/login/aad/callback` to the app registration ([§5](docs/provisioning.md#5-deploy)).
    `--web-redirect-uris` replaces the list, so keep the existing URIs.
13. **Deploy.** Run `azd deploy`. Gate: `curl -s <url>/api/health` returns `{"status":"ok","service":"oz-radio"}` (allow for a cold start).
14. **Smoke test ([§7](docs/provisioning.md#7-smoke-test-checklist)).** Run every item. Use a real browser for sign-in, upload, avatar video/audio, narration, raise-hand Q&A and a render.
    You can drive a browser with Playwright. The human must complete the interactive sign-in if MFA is required.
    If the avatar tile is black, follow [§9](docs/provisioning.md#9-troubleshooting) (TURN/relay). **Don't** change the ICE settings.
15. **Optional, after the human approves:** seed content ([§6.1](docs/provisioning.md#61-first-use)), public demo
    ([§6.2](docs/provisioning.md#62-public-live-demo-optional-off-by-default)) and demo voice Q&A
    ([§6.3](docs/provisioning.md#63-voice-qa-in-the-public-demo-demo_qa_enabled)). Re-run the matching smoke items.
16. **Report** to the human:
    - the environment name, region, resource group and app URL;
    - which smoke items passed, with evidence (screenshot or log excerpt, no secrets);
    - what you set or skipped (budget, tags, custom avatars, seed content, public demo, demo Q&A);
    - the open items: secret expiry date, anything in the runbook that didn't match what you saw.

**Code-only updates afterwards:** `azd deploy`, then re-run the relevant smoke items.
**azd variable or infra changes:** `azd provision`.
