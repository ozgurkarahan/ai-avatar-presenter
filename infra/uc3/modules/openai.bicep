@description('Location for the resource')
param location string

@description('Unique resource token for naming')
param resourceToken string

@description('Tags to apply to every resource')
param tags object

@description('Chat model deployment name')
param chatModelName string = 'gpt-4.1'

@description('Chat model version')
param chatModelVersion string = '2025-04-14'

@description('Chat model TPM capacity (in thousands)')
param chatModelCapacity int = 50

@description('Embedding model deployment name')
param embeddingModelName string = 'text-embedding-3-small'

@description('Embedding model TPM capacity (in thousands)')
param embeddingModelCapacity int = 20

@description('Whether to deploy the embedding model')
param deployEmbedding bool = true

var accountName = 'oai-uc3-${resourceToken}'

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  tags: tags
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAi
  name: chatModelName
  sku: {
    name: 'GlobalStandard'
    capacity: chatModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: chatModelName
      version: chatModelVersion
    }
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = if (deployEmbedding) {
  parent: openAi
  name: embeddingModelName
  sku: {
    name: 'GlobalStandard'
    capacity: embeddingModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: '1'
    }
  }
  dependsOn: [chatDeployment]
}

output endpoint string = openAi.properties.endpoint
output name string = openAi.name
output id string = openAi.id
