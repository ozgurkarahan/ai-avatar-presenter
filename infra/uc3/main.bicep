targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment (used for azd-env-name tag and resource naming salt)')
param environmentName string = 'uc3-podcast'

@minLength(1)
@description('Primary location for all resources. UC3 requires westeurope for DragonHD voice + Batch Avatar Synthesis support.')
param location string = 'westeurope'

@description('Resource group name for the isolated UC3 deployment')
param resourceGroupName string = 'rg-uc3-podcast'

@description('Chat model deployment name')
param chatModelName string = 'gpt-4.1'

@description('Chat model version')
param chatModelVersion string = '2025-04-14'

@description('Chat model TPM capacity (thousands of tokens per minute)')
param chatModelCapacity int = 50

@description('Embedding model deployment name')
param embeddingModelName string = 'text-embedding-3-small'

@description('Embedding model TPM capacity (thousands of tokens per minute)')
param embeddingModelCapacity int = 20

@description('Whether to deploy the embedding model (optional for UC3)')
param deployEmbedding bool = true

@description('Whether to deploy Cosmos DB (PoC uses in-memory state; disable to skip)')
param deployCosmos bool = false

@description('Cosmos DB database name')
param cosmosDatabaseName string = 'podcast-demo'

@description('Cosmos DB container name')
param cosmosContainerName string = 'jobs'

@description('Blob container name for podcast artifacts')
param blobContainerName string = 'podcasts'

@description('Lifecycle: delete blobs after N days')
param blobRetentionDays int = 30

@description('Placeholder container image deployed initially (replaced by CI/CD once real image is built)')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

var abbrs = {
  containerEnv: 'cae-uc3-'
  containerApp: 'ca-uc3-'
  containerRegistry: 'cruc3'
}

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location, resourceGroupName))

// MCAPS-required tags, applied to RG and every child resource.
var commonTags = {
  project: 'ai-presenter-uc3'
  SecurityControl: 'ignore'
  CostControl: 'ignore'
  'azd-env-name': environmentName
}

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: resourceGroupName
  location: location
  tags: commonTags
}

module logs 'modules/log-analytics.bicep' = {
  name: 'uc3-log-analytics'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: commonTags
  }
}

module openai 'modules/openai.bicep' = {
  name: 'uc3-openai'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: commonTags
    chatModelName: chatModelName
    chatModelVersion: chatModelVersion
    chatModelCapacity: chatModelCapacity
    embeddingModelName: embeddingModelName
    embeddingModelCapacity: embeddingModelCapacity
    deployEmbedding: deployEmbedding
  }
}

module aiServices 'modules/ai-services.bicep' = {
  name: 'uc3-ai-services'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: commonTags
  }
}

module cosmos 'modules/cosmos.bicep' = if (deployCosmos) {
  name: 'uc3-cosmos'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: commonTags
    databaseName: cosmosDatabaseName
    containerName: cosmosContainerName
  }
}

module storage 'modules/storage.bicep' = {
  name: 'uc3-storage'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: commonTags
    containerName: blobContainerName
    blobRetentionDays: blobRetentionDays
  }
}

module containerapp 'modules/containerapp.bicep' = {
  name: 'uc3-containerapp'
  scope: rg
  params: {
    envName: '${abbrs.containerEnv}${resourceToken}'
    appName: '${abbrs.containerApp}${resourceToken}'
    acrName: '${abbrs.containerRegistry}${resourceToken}'
    location: location
    tags: commonTags
    containerImage: containerImage
    logAnalyticsCustomerId: logs.outputs.customerId
    logAnalyticsPrimarySharedKey: logs.outputs.primarySharedKey
    speechEndpoint: aiServices.outputs.endpoint
    speechRegion: location
    speechResourceId: aiServices.outputs.resourceId
    openAiEndpoint: openai.outputs.endpoint
    openAiChatDeployment: chatModelName
    cosmosEndpoint: deployCosmos ? cosmos.outputs.endpoint : ''
    cosmosDatabaseName: deployCosmos ? cosmos.outputs.databaseName : ''
    storageAccountName: storage.outputs.name
    blobContainerName: storage.outputs.containerName
  }
}

module roleAssignments 'modules/roles.bicep' = {
  name: 'uc3-roles'
  scope: rg
  params: {
    principalId: containerapp.outputs.principalId
    openAiAccountName: openai.outputs.name
    aiServicesAccountName: aiServices.outputs.name
    storageAccountName: storage.outputs.name
    acrName: containerapp.outputs.acrName
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_LOCATION string = location
output AZURE_OPENAI_ENDPOINT string = openai.outputs.endpoint
output AZURE_OPENAI_CHAT_DEPLOYMENT string = chatModelName
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = deployEmbedding ? embeddingModelName : ''
output AZURE_SPEECH_ENDPOINT string = aiServices.outputs.endpoint
output AZURE_SPEECH_REGION string = location
output AZURE_SPEECH_RESOURCE_ID string = aiServices.outputs.resourceId
output AZURE_COSMOS_ENDPOINT string = deployCosmos ? cosmos.outputs.endpoint : ''
output AZURE_COSMOS_DATABASE string = deployCosmos ? cosmos.outputs.databaseName : ''
output AZURE_COSMOS_CONTAINER string = deployCosmos ? cosmos.outputs.containerName : ''
output AZURE_COSMOS_ACCOUNT_NAME string = deployCosmos ? cosmos.outputs.name : ''
output AZURE_BLOB_ACCOUNT_NAME string = storage.outputs.name
output AZURE_BLOB_CONTAINER string = storage.outputs.containerName
output AZURE_CONTAINER_APP_URL string = containerapp.outputs.url
output AZURE_CONTAINER_APP_NAME string = containerapp.outputs.name
output AZURE_CONTAINER_REGISTRY_LOGIN_SERVER string = containerapp.outputs.acrLoginServer
output AZURE_CONTAINER_REGISTRY_NAME string = containerapp.outputs.acrName
output AZURE_USE_MANAGED_IDENTITY string = 'true'

// Reminder: Cosmos DB data-plane role cannot be assigned via ARM/Bicep.
// Run the command below after deployment so the Container App's managed identity
// can read/write Cosmos documents.
output COSMOS_RBAC_HINT string = deployCosmos ? 'az cosmosdb sql role assignment create --account-name ${cosmos.outputs.name} --resource-group ${rg.name} --scope "/" --principal-id ${containerapp.outputs.principalId} --role-definition-id 00000000-0000-0000-0000-000000000002' : ''
