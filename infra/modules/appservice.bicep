param location string
param environmentName string
param uniqueSuffix string
param tags object
param identityId string
param identityClientId string
param aiServicesEndpoint string
param modelDeploymentName string
param acsConnectionStringSecretUri string
param logAnalyticsWorkspaceName string

// Helper to sanitize environmentName for valid app service name
var sanitizedEnvName = toLower(replace(replace(replace(replace(environmentName, ' ', '-'), '--', '-'), '[^a-zA-Z0-9-]', ''), '_', '-'))
var appServiceName = take('app-${sanitizedEnvName}-${uniqueSuffix}', 60)
var appServicePlanName = take('asp-${sanitizedEnvName}-${uniqueSuffix}', 60)

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = { 
  name: logAnalyticsWorkspaceName 
}

// App Service Plan (Linux)
resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: appServicePlanName
  location: location
  tags: tags
  sku: {
    name: 'B1'
    tier: 'Basic'
    capacity: 1
  }
  kind: 'linux'
  properties: {
    reserved: true // Required for Linux
  }
}

// App Service
resource appService 'Microsoft.Web/sites@2023-12-01' = {
  name: appServiceName
  location: location
  tags: union(tags, { 'azd-service-name': 'app' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    keyVaultReferenceIdentity: identityId
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appCommandLine: 'hypercorn server:app --bind 0.0.0.0:8000 --workers 4'
      appSettings: [
        {
          name: 'AZURE_VOICE_LIVE_ENDPOINT'
          value: aiServicesEndpoint
        }
        {
          name: 'VOICE_LIVE_MODEL'
          value: modelDeploymentName
        }
        {
          name: 'ACS_CONNECTION_STRING'
          value: '@Microsoft.KeyVault(SecretUri=${acsConnectionStringSecretUri})'
        }
        {
          name: 'AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID'
          value: identityClientId
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'ENABLE_ORYX_BUILD'
          value: 'true'
        }
        {
          name: 'PORT'
          value: '8000'
        }
        {
          name: 'WEBSITES_PORT'
          value: '8000'
        }
      ]
    }
  }
}

// Diagnostic settings for App Service
resource appServiceDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: '${appServiceName}-diagnostics'
  scope: appService
  properties: {
    workspaceId: logAnalyticsWorkspace.id
    logs: [
      {
        category: 'AppServiceHTTPLogs'
        enabled: true
      }
      {
        category: 'AppServiceConsoleLogs'
        enabled: true
      }
      {
        category: 'AppServiceAppLogs'
        enabled: true
      }
      {
        category: 'AppServicePlatformLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

output appServiceId string = appService.id
output appServiceName string = appService.name
output appServiceHostName string = appService.properties.defaultHostName
output appServiceUrl string = 'https://${appService.properties.defaultHostName}'
