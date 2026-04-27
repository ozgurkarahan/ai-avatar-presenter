@description('Name of the Container App Environment')
param envName string

@description('Name of the Container App')
param appName string

@description('Name of the Container Registry')
param acrName string

@description('Location for the resource')
param location string

@description('Tags to apply to every resource')
param tags object

@description('Container image to deploy (placeholder until real image is pushed)')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Target container port')
param targetPort int = 8000

@description('Log Analytics workspace customer/workspace id')
param logAnalyticsCustomerId string

@description('Log Analytics workspace primary shared key')
@secure()
param logAnalyticsPrimarySharedKey string

@description('Azure Speech / AI Services endpoint')
param speechEndpoint string

@description('Azure Speech region')
param speechRegion string

@description('Azure Speech resource ID (for AAD token exchange)')
param speechResourceId string

@description('Azure OpenAI endpoint')
param openAiEndpoint string

@description('Azure OpenAI chat deployment name')
param openAiChatDeployment string

@description('Azure Cosmos DB endpoint')
param cosmosEndpoint string

@description('Azure Cosmos DB database name')
param cosmosDatabaseName string

@description('Azure Storage Account name')
param storageAccountName string

@description('Azure Blob container name')
param blobContainerName string

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsPrimarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: union(tags, {
    'azd-service-name': 'backend'
  })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
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
            { name: 'AZURE_USE_MANAGED_IDENTITY', value: 'true' }
            { name: 'AZURE_COSMOS_ENDPOINT', value: cosmosEndpoint }
            { name: 'AZURE_COSMOS_DATABASE', value: cosmosDatabaseName }
            { name: 'AZURE_BLOB_ACCOUNT_NAME', value: storageAccountName }
            { name: 'AZURE_BLOB_CONTAINER', value: blobContainerName }
          ]
        }
      ]
      scale: {
        minReplicas: 0
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
}

output url string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output name string = containerApp.name
output principalId string = containerApp.identity.principalId
output acrName string = acr.name
output acrId string = acr.id
output acrLoginServer string = acr.properties.loginServer
