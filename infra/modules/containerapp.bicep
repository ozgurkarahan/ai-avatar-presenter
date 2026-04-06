@description('Name of the Container App Environment')
param envName string

@description('Name of the Container App')
param appName string

@description('Name of the Container Registry')
param acrName string

@description('Location for the resource')
param location string

@description('Container image to deploy')
param containerImage string

@description('Azure Speech endpoint')
param speechEndpoint string

@description('Azure Speech region')
param speechRegion string

@description('Azure Speech resource ID (for AAD token exchange)')
param speechResourceId string

@description('Azure OpenAI endpoint')
param openAiEndpoint string

@description('Azure OpenAI chat deployment name')
param openAiChatDeployment string

@description('Azure OpenAI embedding deployment name')
param openAiEmbeddingDeployment string

@description('Azure Cosmos DB endpoint')
param cosmosEndpoint string

@description('Azure Storage Account name')
param storageAccountName string

@description('Azure Blob container name')
param blobContainerName string = 'slide-images'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
  tags: {
    project: 'ai-presenter'
  }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${envName}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource containerEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
  tags: {
    project: 'ai-presenter'
  }
}

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: appName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      secrets: [
        { name: 'acr-password', value: acr.listCredentials().passwords[0].value }
      ]
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: containerImage
          resources: {
            cpu: json('1')
            memory: '2Gi'
          }
          env: [
            { name: 'AZURE_SPEECH_ENDPOINT', value: speechEndpoint }
            { name: 'AZURE_SPEECH_REGION', value: speechRegion }
            { name: 'AZURE_SPEECH_RESOURCE_ID', value: speechResourceId }
            { name: 'AZURE_OPENAI_ENDPOINT', value: openAiEndpoint }
            { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT', value: openAiChatDeployment }
            { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: openAiEmbeddingDeployment }
            { name: 'AZURE_USE_MANAGED_IDENTITY', value: 'true' }
            { name: 'USE_LOCAL_SEARCH', value: 'true' }
            { name: 'AZURE_COSMOS_ENDPOINT', value: cosmosEndpoint }
            { name: 'AZURE_BLOB_ACCOUNT_NAME', value: storageAccountName }
            { name: 'AZURE_BLOB_CONTAINER', value: blobContainerName }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
  tags: {
    'azd-service-name': 'backend'
    project: 'ai-presenter'
  }
}

output url string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output name string = containerApp.name
output principalId string = containerApp.identity.principalId
output acrLoginServer string = acr.properties.loginServer
