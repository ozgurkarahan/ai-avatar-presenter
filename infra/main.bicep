targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment (used for resource naming)')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Chat model deployment name')
param chatModelName string = 'gpt-4.1'

@description('Embedding model deployment name')
param embeddingModelName string = 'text-embedding-3-small'

@description('Microsoft Entra ID App Registration client ID for Easy Auth (leave empty to disable)')
param authClientId string = ''

var abbrs = {
  resourceGroup: 'rg-'
  containerEnv: 'cae-'
  containerApp: 'ca-'
  containerRegistry: 'cr'
}

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: '${abbrs.resourceGroup}${environmentName}'
  location: location
  tags: {
    'azd-env-name': environmentName
    project: 'ai-presenter'
  }
}

// Provision Azure OpenAI with model deployments
module openai 'modules/openai.bicep' = {
  name: 'openai'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    chatModelName: chatModelName
    embeddingModelName: embeddingModelName
  }
}

// Provision Azure AI Services (Speech/Avatar)
module aiServices 'modules/ai-services.bicep' = {
  name: 'aiServices'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
  }
}

// Provision Cosmos DB (presentation persistence)
module cosmos 'modules/cosmos.bicep' = {
  name: 'cosmos'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
  }
}

// Provision Storage Account (slide images)
module storage 'modules/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
  }
}

module containerapp 'modules/containerapp.bicep' = {
  name: 'containerapp'
  scope: rg
  params: {
    envName: '${abbrs.containerEnv}${resourceToken}'
    appName: '${abbrs.containerApp}${resourceToken}'
    acrName: '${abbrs.containerRegistry}${resourceToken}'
    location: location
    containerImage: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    speechEndpoint: aiServices.outputs.endpoint
    speechRegion: location
    speechResourceId: aiServices.outputs.resourceId
    openAiEndpoint: openai.outputs.endpoint
    openAiChatDeployment: chatModelName
    openAiEmbeddingDeployment: embeddingModelName
    cosmosEndpoint: cosmos.outputs.endpoint
    storageAccountName: storage.outputs.name
    authClientId: authClientId
  }
}

// Role assignments for managed identity
module roleAssignments 'modules/roles.bicep' = {
  name: 'roleAssignments'
  scope: rg
  params: {
    principalId: containerapp.outputs.principalId
    openAiAccountName: openai.outputs.name
    aiServicesAccountName: aiServices.outputs.name
    cosmosAccountName: cosmos.outputs.name
    storageAccountName: storage.outputs.name
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_LOCATION string = location
output AZURE_SPEECH_ENDPOINT string = aiServices.outputs.endpoint
output AZURE_SPEECH_REGION string = location
output AZURE_SPEECH_RESOURCE_ID string = aiServices.outputs.resourceId
output AZURE_OPENAI_ENDPOINT string = openai.outputs.endpoint
output AZURE_OPENAI_CHAT_DEPLOYMENT string = chatModelName
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = embeddingModelName
output AZURE_COSMOS_ENDPOINT string = cosmos.outputs.endpoint
output AZURE_BLOB_ACCOUNT_NAME string = storage.outputs.name
output AZURE_CONTAINER_APP_URL string = containerapp.outputs.url
output AZURE_CONTAINER_REGISTRY_LOGIN_SERVER string = containerapp.outputs.acrLoginServer
