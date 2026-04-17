@description('Location for the resource')
param location string

@description('Unique resource token for naming')
param resourceToken string

@description('Tags to apply to every resource')
param tags object

@description('Blob container name')
param containerName string = 'podcasts'

@description('Number of days after which blobs are auto-deleted')
param blobRetentionDays int = 30

var accountName = 'stuc3${resourceToken}'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: accountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  tags: tags
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource podcastsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}

resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'delete-old-podcasts'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: [containerName]
            }
            actions: {
              baseBlob: {
                delete: {
                  daysAfterModificationGreaterThan: blobRetentionDays
                }
              }
            }
          }
        }
      ]
    }
  }
}

output name string = storageAccount.name
output id string = storageAccount.id
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
output containerName string = containerName
