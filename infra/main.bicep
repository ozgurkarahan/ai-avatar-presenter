targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment (used for resource naming)')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Name of the existing Azure OpenAI account')
param openAiAccountName string = ''

@description('Name of the existing Azure AI Services account (Speech/Avatar)')
param aiServicesAccountName string = ''

@description('Chat model deployment name')
param chatModelName string = 'gpt-4.1'

@description('Embedding model deployment name')
param embeddingModelName string = 'text-embedding-3-small'

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

// Reference existing AI resources (created manually via az CLI)
module existingResources 'modules/existing-ai.bicep' = {
  name: 'existingResources'
  scope: rg
  params: {
    openAiAccountName: openAiAccountName
    aiServicesAccountName: aiServicesAccountName
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
    speechEndpoint: existingResources.outputs.aiServicesEndpoint
    speechRegion: location
    speechResourceId: existingResources.outputs.aiServicesResourceId
    openAiEndpoint: existingResources.outputs.openAiEndpoint
    openAiChatDeployment: chatModelName
    openAiEmbeddingDeployment: embeddingModelName
  }
}

// Role assignments for managed identity on existing AI resources
module roleAssignments 'modules/roles.bicep' = {
  name: 'roleAssignments'
  scope: rg
  params: {
    principalId: containerapp.outputs.principalId
    openAiAccountName: openAiAccountName
    aiServicesAccountName: aiServicesAccountName
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_LOCATION string = location
output AZURE_SPEECH_ENDPOINT string = existingResources.outputs.aiServicesEndpoint
output AZURE_SPEECH_REGION string = location
output AZURE_SPEECH_RESOURCE_ID string = existingResources.outputs.aiServicesResourceId
output AZURE_OPENAI_ENDPOINT string = existingResources.outputs.openAiEndpoint
output AZURE_OPENAI_CHAT_DEPLOYMENT string = chatModelName
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = embeddingModelName
output AZURE_CONTAINER_APP_URL string = containerapp.outputs.url
output AZURE_CONTAINER_REGISTRY_LOGIN_SERVER string = containerapp.outputs.acrLoginServer
