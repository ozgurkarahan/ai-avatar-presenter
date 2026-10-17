# Deploying a parallel DeckFM instance

> This page used to describe a "copilot" instance that reused existing Azure
> OpenAI and AI Speech resources through `openAiAccountName` /
> `aiServicesAccountName`. Those parameters no longer exist in `infra/`.

To deploy a separate instance, follow **[provisioning.md](provisioning.md)** with a new azd environment:

```bash
azd env new <second-env-name>     # creates its own rg-<second-env-name>
# set AUTH_* / ALLOWED_OBJECT_IDS etc. as in provisioning.md §3–§4
azd up
```

- Every azd environment gets its **own** resource group: identity, ACR, Azure OpenAI, Cosmos DB, Storage, Log Analytics and Container App.
- Azure OpenAI is always created per environment. Make sure you have enough quota for each environment ([provisioning.md §2.5](provisioning.md#25-quota)).
- To **share** an existing Speech / AI Services resource (for example one hosting custom photo avatars), set
  `USE_EXTERNAL_AI_SERVICES=true` and `EXTERNAL_AI_SERVICES_ENDPOINT` / `_REGION` / `_RESOURCE_ID`
  ([provisioning.md §4](provisioning.md#4-azd-environment-variables)).
- Each instance needs its redirect URI (`https://<app-fqdn>/.auth/login/aad/callback`). Add it to a separate app registration, or add it to the same one.
- Teams packaging: `.\scripts\package-teams-app.ps1 -Hostname "<app-fqdn>"` (see [teams-integration.md](teams-integration.md)).

Coding agents: follow [BOOTSTRAP.md](../BOOTSTRAP.md).
