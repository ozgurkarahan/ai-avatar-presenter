@description('Name of the existing Azure OpenAI account')
param openAiAccountName string

@description('Name of the existing Azure AI Services account')
param aiServicesAccountName string

resource openAi 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' existing = {
  name: openAiAccountName
}

resource aiServices 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' existing = {
  name: aiServicesAccountName
}

output openAiEndpoint string = openAi.properties.endpoint
output openAiName string = openAi.name
output aiServicesEndpoint string = aiServices.properties.endpoint
output aiServicesName string = aiServices.name
output aiServicesResourceId string = aiServices.id
