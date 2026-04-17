@description('Principal ID of the Container App managed identity')
param principalId string

@description('Name of the OpenAI account')
param openAiAccountName string

@description('Name of the Azure AI Services account (Speech/Avatar)')
param aiServicesAccountName string

@description('Name of the Storage account')
param storageAccountName string

@description('Name of the Azure Container Registry')
param acrName string

// Cognitive Services Speech User — token issuance + TTS + Batch Avatar
var cognitiveServicesSpeechUserRole = 'f2dc8367-1007-4938-bd23-fe263f013447'

// Cognitive Services OpenAI User — chat completions + embeddings
var cognitiveServicesOpenAiUserRole = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

// Cognitive Services User — broad access for cognitive services APIs
var cognitiveServicesUserRole = 'a97b65f3-24c7-4388-baec-2e87135dc908'

// Storage Blob Data Contributor
var storageBlobDataContributorRole = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

// AcrPull
var acrPullRole = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiServicesAccountName
}

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: openAiAccountName
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}

resource aiServicesSpeechRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, principalId, cognitiveServicesSpeechUserRole)
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesSpeechUserRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource aiServicesCogUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, principalId, cognitiveServicesUserRole)
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource openAiUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAiAccount.id, principalId, cognitiveServicesOpenAiUserRole)
  scope: openAiAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAiUserRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, principalId, storageBlobDataContributorRole)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, principalId, acrPullRole)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
