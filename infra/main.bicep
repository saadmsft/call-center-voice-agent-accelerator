targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the the environment which is used to generate a short unique hash used in all resources.')
param environmentName string

@minLength(1)
@description('Primary location for all resources (filtered on available regions for Azure Open AI Service).')
@allowed([
  'eastus2'
  'swedencentral'
])
param location string

var abbrs = loadJsonContent('./abbreviations.json')
param useApplicationInsights bool = true
param appExists bool
@description('The OpenAI model name')
param modelName string = ' gpt-4o-mini'
@description('Id of the user or app to assign application roles. If ommited will be generated from the user assigned identity.')
param principalId string = ''
@description('Resource ID of existing Azure Communication Services. If provided, will use existing ACS instead of creating new one.')
param existingAcsResourceId string = ''
@description('Connection string for existing ACS. Required if existingAcsResourceId is provided.')
@secure()
param existingAcsConnectionString string = ''
@description('Resource ID of existing AI Services. If provided, will use existing AI Services instead of creating new one.')
param existingAiServicesResourceId string = ''
@description('Endpoint for existing AI Services. Required if existingAiServicesResourceId is provided.')
param existingAiServicesEndpoint string = ''

var uniqueSuffix = substring(uniqueString(subscription().id, environmentName), 0, 5)
var tags = {'azd-env-name': environmentName }
var rgName = 'rg-${environmentName}-${uniqueSuffix}'

resource rg 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: rgName
  location: location
  tags: tags
}

// [ User Assigned Identity for App to avoid circular dependency ]
module appIdentity './modules/identity.bicep' = {
  name: 'uami'
  scope: rg
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
  }
}

var sanitizedEnvName = toLower(replace(replace(replace(replace(environmentName, ' ', '-'), '--', '-'), '[^a-zA-Z0-9-]', ''), '_', '-'))
var logAnalyticsName = take('log-${sanitizedEnvName}-${uniqueSuffix}', 63)
var appInsightsName = take('insights-${sanitizedEnvName}-${uniqueSuffix}', 63)
module monitoring 'modules/monitoring/monitor.bicep' = {
  name: 'monitor'
  scope: rg
  params: {
    logAnalyticsName: logAnalyticsName
    appInsightsName: appInsightsName
    tags: tags
  }
}

module aiServices 'modules/aiservices.bicep' = if (empty(existingAiServicesResourceId)) {
  name: 'ai-foundry-deployment'
  scope: rg
  params: {
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    identityId: appIdentity.outputs.identityId
    tags: tags
  }
}

module acs 'modules/acs.bicep' = if (empty(existingAcsResourceId)) {
  name: 'acs-deployment'
  scope: rg
  params: {
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
  }
}

var keyVaultName = toLower(replace('kv-${environmentName}-${uniqueSuffix}', '_', '-'))
var sanitizedKeyVaultName = take(toLower(replace(replace(replace(replace(keyVaultName, '--', '-'), '_', '-'), '[^a-zA-Z0-9-]', ''), '-$', '')), 24)

// Configuration for using existing resources vs creating new ones
// Note: The Bicep linter may show warnings about potential null values in conditional expressions.
// These are false positives - the ternary operators ensure only one branch executes at deployment time.
// When existingAcsResourceId is empty, new ACS is created and its outputs are used.
// When existingAcsResourceId is provided, the existing resource values are used instead.

module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault-deployment'
  scope: rg
  params: {
    location: location
    keyVaultName: sanitizedKeyVaultName
    tags: tags
    acsConnectionString: empty(existingAcsResourceId) ? acs.outputs.acsConnectionString : existingAcsConnectionString
  }
}

// Add role assignments
module RoleAssignments 'modules/roleassignments.bicep' = {
  scope: rg
  name: 'role-assignments'
  params: {
    identityPrincipalId: appIdentity.outputs.principalId
    aiServicesId: empty(existingAiServicesResourceId) ? aiServices.outputs.aiServicesId : existingAiServicesResourceId
    keyVaultName: sanitizedKeyVaultName
  }
}

module appService 'modules/appservice.bicep' = {
  name: 'appservice-deployment'
  scope: rg
  params: {
    location: location
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    tags: tags
    identityId: appIdentity.outputs.identityId
    identityClientId: appIdentity.outputs.clientId
    aiServicesEndpoint: empty(existingAiServicesResourceId) ? aiServices.outputs.aiServicesEndpoint : existingAiServicesEndpoint
    modelDeploymentName: modelName
    acsConnectionStringSecretUri: keyvault.outputs.acsConnectionStringUri
    logAnalyticsWorkspaceName: logAnalyticsName
  }
}


// OUTPUTS will be saved in azd env for later use
output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_USER_ASSIGNED_IDENTITY_ID string = appIdentity.outputs.identityId
output AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID string = appIdentity.outputs.clientId

output AZURE_APP_SERVICE_NAME string = appService.outputs.appServiceName
output AZURE_APP_SERVICE_URL string = appService.outputs.appServiceUrl
output SERVICE_API_ENDPOINTS array = ['${appService.outputs.appServiceUrl}/acs/incomingcall']
output AZURE_VOICE_LIVE_MODEL string = modelName
// Note: These outputs use conditional logic and may show linter warnings, but will work correctly at deployment time
output AZURE_ACS_RESOURCE_ID string = existingAcsResourceId != '' ? existingAcsResourceId : (acs.outputs.acsResourceId ?? '')
output AZURE_AI_SERVICES_RESOURCE_ID string = existingAiServicesResourceId != '' ? existingAiServicesResourceId : (aiServices.outputs.aiServicesId ?? '')
