@description('Location for the resource')
param location string

@description('Unique resource token for naming')
param resourceToken string

@description('Tags to apply to the resource')
param tags object = {}

var accountName = 'ais-${resourceToken}'

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
  tags: tags
}

output endpoint string = aiServices.properties.endpoint
output name string = aiServices.name
output resourceId string = aiServices.id
