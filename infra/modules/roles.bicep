@description('Principal ID of the Container App managed identity')
param principalId string

@description('Name of the existing OpenAI account')
param openAiAccountName string

@description('Name of the existing Azure AI Services account (Speech/Avatar)')
param aiServicesAccountName string

// Cognitive Services Speech User — allows token issuance and TTS
var cognitiveServicesSpeechUserRole = 'f2dc8367-1007-4938-bd23-fe263f013447'

// Cognitive Services OpenAI User — allows chat completions and embeddings
var cognitiveServicesOpenAiUserRole = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

// Cognitive Services User — broad access for cognitive services
var cognitiveServicesUserRole = 'a97b65f3-24c7-4388-baec-2e87135dc908'

resource aiServices 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' existing = {
  name: aiServicesAccountName
}

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' existing = {
  name: openAiAccountName
}

// AI Services: Speech User (token issuance + TTS)
resource aiServicesSpeechRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, principalId, cognitiveServicesSpeechUserRole)
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesSpeechUserRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// AI Services: Cognitive Services User (broad access for avatar APIs)
resource aiServicesCogUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, principalId, cognitiveServicesUserRole)
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

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
