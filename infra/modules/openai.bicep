@description('Location for the resource')
param location string

@description('Unique resource token for naming')
param resourceToken string

@description('Chat model deployment name')
param chatModelName string = 'gpt-4.1'

@description('Embedding model deployment name')
param embeddingModelName string = 'text-embedding-3-small'

var accountName = 'oai-${resourceToken}'

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
  }
  tags: {
    project: 'ai-presenter'
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAi
  name: chatModelName
  sku: {
    name: 'GlobalStandard'
    capacity: 80
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: chatModelName
      version: '2025-04-14'
    }
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAi
  name: embeddingModelName
  sku: {
    name: 'GlobalStandard'
    capacity: 120
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
