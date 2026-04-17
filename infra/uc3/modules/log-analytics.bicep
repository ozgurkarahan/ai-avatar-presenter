@description('Location for the resource')
param location string

@description('Unique resource token for naming')
param resourceToken string

@description('Tags to apply to every resource')
param tags object

var workspaceName = 'log-uc3-${resourceToken}'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

output id string = logAnalytics.id
output customerId string = logAnalytics.properties.customerId
#disable-next-line outputs-should-not-contain-secrets
output primarySharedKey string = logAnalytics.listKeys().primarySharedKey
output name string = logAnalytics.name
