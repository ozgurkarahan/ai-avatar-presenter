# UC3 — Podcast dual-avatar demo infrastructure

Isolated, single-region Bicep deployment for the UC3 presales PoC. Everything
lives in its own resource group (`rg-uc3-podcast`) so it can be torn down with
a single command without touching the main `ai-presenter` stack.

## What gets provisioned

| Resource | Purpose |
|---|---|
| Azure OpenAI (`oai-uc3-*`) | `gpt-4.1` (50K TPM) + `text-embedding-3-small` (20K TPM, optional) |
| Azure AI Services (`ais-uc3-*`, kind=AIServices) | Speech + Batch Avatar Synthesis (DragonHD voices) — westeurope |
| Storage Account (`stuc3*`) | Blob container `podcasts`, private, 30-day lifecycle delete |
| Cosmos DB (`cosmos-uc3-*`) | Serverless SQL API, db `podcast-demo`, container `jobs` partitioned by `/id` |
| Container Apps Environment + Container App | Web + render backend (placeholder image until CI pushes real one) |
| Azure Container Registry (`cruc3*`, Basic) | Backend image registry |
| Log Analytics Workspace | 30-day retention, PerGB2018 |

The Container App runs with a **system-assigned managed identity** that receives:
- `Cognitive Services OpenAI User` on the OpenAI account
- `Cognitive Services User` + `Cognitive Services Speech User` on the AI Services account
- `Storage Blob Data Contributor` on the storage account
- `AcrPull` on the ACR

> ⚠️ The Cosmos DB **data-plane** role (`00000000-0000-0000-0000-000000000002`)
> cannot be assigned via ARM/Bicep. `deploy.ps1` prints the exact `az` command
> to run post-deploy — also available in the `COSMOS_RBAC_HINT` deployment output.

## Tags (MCAPS policy)

Applied to the resource group and every child resource:

- `project = ai-presenter-uc3`
- `SecurityControl = ignore`
- `CostControl = ignore`
- `azd-env-name = <environmentName>` (default: `uc3-podcast`)

## Prerequisites

- Azure CLI (`az`) logged in to the target subscription
- Bicep CLI (bundled with recent `az`) — verify with `az bicep version`
- PowerShell 7+ (`pwsh`)
- Subscription quota for:
  - Azure OpenAI `gpt-4.1` GlobalStandard in westeurope
  - Batch Avatar Synthesis on AI Services in westeurope
  - Container Apps Environment in westeurope

## Deploy

```powershell
cd infra/uc3
./deploy.ps1
# optionally: ./deploy.ps1 -SubscriptionId <sub-guid>
```

`deploy.ps1` will:

1. `az bicep build` the template (local validation).
2. `az deployment sub create` into the target subscription.
3. Read outputs and write every `AZURE_*` key to `demos/backend/.env.uc3`
   in KEY=VALUE format.
4. Print the Cosmos data-plane RBAC command to run manually.

## Validate without deploying

```powershell
az bicep build --file infra/uc3/main.bicep
az deployment sub validate `
  --location westeurope `
  --template-file infra/uc3/main.bicep `
  --parameters "@infra/uc3/main.parameters.json"
```

## Post-deploy: assign Cosmos data-plane role

The exact command is printed by `deploy.ps1`, e.g.:

```powershell
az cosmosdb sql role assignment create `
  --account-name <cosmos-uc3-...> `
  --resource-group rg-uc3-podcast `
  --scope "/" `
  --principal-id <container-app-principal-id> `
  --role-definition-id 00000000-0000-0000-0000-000000000002
```

## Push the real backend image

The container app starts with the Microsoft hello-world image as a placeholder.
Once the UC3 backend image is built:

```powershell
$acr = (az deployment sub show -n <deployment-name> --query properties.outputs.AZURE_CONTAINER_REGISTRY_NAME.value -o tsv)
az acr login --name $acr
docker tag uc3-backend:local "$acr.azurecr.io/uc3-backend:latest"
docker push "$acr.azurecr.io/uc3-backend:latest"

az containerapp update `
  --name <container-app-name> `
  --resource-group rg-uc3-podcast `
  --image "$acr.azurecr.io/uc3-backend:latest"
```

## Teardown

```powershell
./teardown.ps1
```

This deletes `rg-uc3-podcast` asynchronously. If you plan to redeploy with the
same names, also purge soft-deleted Cognitive Services accounts:

```powershell
az cognitiveservices account purge --location westeurope --resource-group rg-uc3-podcast --name <oai-uc3-...>
az cognitiveservices account purge --location westeurope --resource-group rg-uc3-podcast --name <ais-uc3-...>
```

## Outputs

`main.bicep` emits the following outputs (all written to `.env.uc3` by `deploy.ps1`):

- `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- `AZURE_SPEECH_ENDPOINT`, `AZURE_SPEECH_REGION`, `AZURE_SPEECH_RESOURCE_ID`
- `AZURE_COSMOS_ENDPOINT`, `AZURE_COSMOS_DATABASE`, `AZURE_COSMOS_CONTAINER`, `AZURE_COSMOS_ACCOUNT_NAME`
- `AZURE_BLOB_ACCOUNT_NAME`, `AZURE_BLOB_CONTAINER`
- `AZURE_CONTAINER_APP_URL`, `AZURE_CONTAINER_APP_NAME`
- `AZURE_CONTAINER_REGISTRY_LOGIN_SERVER`, `AZURE_CONTAINER_REGISTRY_NAME`
- `AZURE_USE_MANAGED_IDENTITY = 'true'`

Plus the non-`AZURE_*` helper output `COSMOS_RBAC_HINT`.
