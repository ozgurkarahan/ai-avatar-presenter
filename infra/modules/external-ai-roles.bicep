// Role assignments on a pre-existing (external) AI Services / Speech resource,
// possibly in another resource group of the same subscription. The deploying
// principal needs Owner or User Access Administrator on that resource group.

@description('Name of the existing AI Services account (in this module\'s resource group scope)')
param accountName string

@description('Principal ID of the app managed identity')
param principalId string

var roles = [
  'a97b65f3-24c7-4388-baec-2e87135dc908' // Cognitive Services User
  'f2dc8367-1007-4938-bd23-fe263f013447' // Cognitive Services Speech User
  '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Foundry User (formerly Azure AI User) — Voice Live (ai.azure.com scope)
]

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: accountName
}

resource assignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for role in roles: {
    name: guid(account.id, principalId, role)
    scope: account
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
      principalId: principalId
      principalType: 'ServicePrincipal'
    }
  }
]
