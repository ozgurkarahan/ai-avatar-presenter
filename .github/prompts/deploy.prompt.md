---
mode: agent
description: Provision and deploy Oz Radio to Azure with azd by following BOOTSTRAP.md, with human checkpoints and a browser smoke test.
---

# Deploy Oz Radio to Azure

Follow [`BOOTSTRAP.md`](../../BOOTSTRAP.md) exactly, step by step. Use
[`docs/provisioning.md`](../../docs/provisioning.md) as the reference for every step.

- Start by reading `BOOTSTRAP.md`, `docs/provisioning.md`, `azure.yaml`, `infra/main.parameters.json` and `hooks/preprovision.*`.
- Stop and ask the human at every 🛑 point:
  - tenant and subscription;
  - region;
  - Entra app registration and secret;
  - `ALLOWED_OBJECT_IDS`;
  - budget recipients;
  - tags;
  - custom photo avatars (`CUSTOM_AVATARS_JSON`, `HIDE_STOCK_AVATARS`);
  - seed content;
  - public demo (`PUBLIC_DEMO_ENABLED`) and demo voice Q&A (`DEMO_QA_ENABLED`, only after the smoke test passes);
  - quota or policy issues;
  - any change to `infra/`.
- Never print or commit secrets. Never set `AUTH_MODE=disabled` or `ALLOW_INSECURE_NO_AUTH=true` in Azure. Never weaken auth, RBAC, storage, ICE relay or quota settings to make a check pass.
- Don't create new script files. Run the documented commands directly.
- Verify each gate before you continue. You're done only when the smoke-test checklist (`docs/provisioning.md` §7) passes in a real browser, including the admin raise-hand Q&A item.
- Finish with the report described in the last step of `BOOTSTRAP.md`.

Environment name to use (ask if empty): `${input:envName}`
