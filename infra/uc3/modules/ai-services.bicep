@description('Location for the resource')
param location string

@description('Unique resource token for naming')
param resourceToken string

@description('Tags to apply to every resource')
param tags object

var accountName = 'ais-uc3-${resourceToken}'

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  tags: tags
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
  }
}

output endpoint string = aiServices.properties.endpoint
output name string = aiServices.name
output resourceId string = aiServices.id
