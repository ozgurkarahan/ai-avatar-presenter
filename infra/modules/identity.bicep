@description('Location for the resource')
param location string

@description('Name of the user-assigned managed identity')
param identityName string

@description('Tags to apply to the resource')
param tags object = {}

// Created before the Container App so that AcrPull and all data-plane roles
// exist before the first revision pulls a private image or calls a service.
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
  tags: tags
}

output id string = identity.id
output name string = identity.name
output principalId string = identity.properties.principalId
output clientId string = identity.properties.clientId
