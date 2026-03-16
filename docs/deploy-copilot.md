# Deploying AI Presenter (Copilot Instance)

## Overview

This guide deploys a **parallel instance** of AI Presenter to Azure with the "copilot" suffix.
It creates its own Container App and Registry but **reuses the existing Azure OpenAI and AI Speech services**.

## Prerequisites

- Azure CLI (`az login` completed)
- Azure Developer CLI (`azd`) installed
- Access to the existing Azure OpenAI and AI Services resources

## Deployment Steps

### 1. Create the copilot environment

```bash
azd env new ai-presenter-copilot
```

### 2. Set required environment variables

```bash
azd env set AZURE_LOCATION swedencentral
azd env set openAiAccountName <your-existing-openai-account-name>
azd env set aiServicesAccountName <your-existing-ai-services-account-name>
```

> **Note**: `openAiAccountName` and `aiServicesAccountName` must reference the **same existing** Azure resources used by the main deployment. No new AI resources are created.

### 3. Deploy

```bash
azd up
```

This provisions:
- **New resources** (copilot-isolated):
  - Resource Group: `rg-ai-presenter-copilot`
  - Container App Environment + Container App
  - Container Registry
  - Log Analytics Workspace
- **Shared resources** (existing, not duplicated):
  - Azure OpenAI (GPT-4.1, text-embedding-3-small deployments)
  - Azure AI Services / Speech (Avatar TTS, VoiceLive)

### 4. Get the deployed URL

```bash
azd env get-values | Select-String "AZURE_CONTAINER_APP_URL"
```

## Resource Naming Convention

| Resource | Name Pattern |
|----------|-------------|
| Resource Group | `rg-ai-presenter-copilot` |
| Container App | `ca-<unique-token>` |
| Container Registry | `cr<unique-token>` |
| Log Analytics | `cae-<unique-token>-logs` |

## Coexistence

This deployment coexists with:
- **Base deployment** (`ai-presenter`) — the original instance
- **Claude deployment** (`ai-presenter-claude`) — parallel instance from Claude Code agent

All three share the same Azure OpenAI and AI Speech resources.

## Teams Integration

After deployment, package the Teams app with the Container App URL:

```powershell
.\scripts\package-teams-app.ps1 -Hostname "<your-container-app-fqdn>"
```

Then sideload the generated `teams-app-package.zip` in Microsoft Teams.
