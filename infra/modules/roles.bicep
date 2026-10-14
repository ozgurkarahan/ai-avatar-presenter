@description('Principal ID of the app user-assigned managed identity')
param principalId string

@description('Name of the OpenAI account')
param openAiAccountName string

@description('Name of the Azure AI Services account (Speech/Avatar) — leave empty when using an external resource (see external-ai-roles.bicep)')
param aiServicesAccountName string

@description('Name of the Cosmos DB account')
param cosmosAccountName string

@description('Name of the Storage account')
param storageAccountName string

// Cognitive Services Speech User — allows token issuance and TTS
var cognitiveServicesSpeechUserRole = 'f2dc8367-1007-4938-bd23-fe263f013447'

// Cognitive Services OpenAI User — allows chat completions and embeddings
var cognitiveServicesOpenAiUserRole = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

// Cognitive Services User — broad data-plane access for cognitive services
var cognitiveServicesUserRole = 'a97b65f3-24c7-4388-baec-2e87135dc908'

// Foundry User (formerly Azure AI User) — required by Voice Live (https://ai.azure.com/.default)
var foundryUserRole = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

// Cosmos DB Built-in Data Contributor
var cosmosDbDataContributorRole = '00000000-0000-0000-0000-000000000002'

// Storage Blob Data Contributor (includes user-delegation-key generation)
var storageBlobDataContributorRole = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

var aiServicesRoles = [
  cognitiveServicesSpeechUserRole
  cognitiveServicesUserRole
  foundryUserRole
]

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = if (!empty(aiServicesAccountName)) {
  name: aiServicesAccountName
}

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: openAiAccountName
}

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosAccountName
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

// AI Services: Speech User + Cognitive Services User + Foundry User
resource aiServicesRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for role in aiServicesRoles: if (!empty(aiServicesAccountName)) {
    name: guid(aiServices.id, principalId, role)
    scope: aiServices
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
      principalId: principalId
      principalType: 'ServicePrincipal'
    }
  }
]

// OpenAI: OpenAI User (chat completions + embeddings)
resource openAiUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAiAccount.id, principalId, cognitiveServicesOpenAiUserRole)
  scope: openAiAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAiUserRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Cosmos DB: Data Contributor (read/write documents)
resource cosmosDataContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, principalId, cosmosDbDataContributorRole)
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/${cosmosDbDataContributorRole}'
    principalId: principalId
    scope: cosmosAccount.id
  }
}

// Storage: Blob Data Contributor (read/write blobs + user delegation SAS)
resource storageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, principalId, storageBlobDataContributorRole)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
