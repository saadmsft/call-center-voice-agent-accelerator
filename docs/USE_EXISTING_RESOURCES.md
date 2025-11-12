# Using Existing Azure Resources

You can configure this accelerator to use existing Azure Communication Services (ACS) and AI Services (Azure OpenAI) resources instead of creating new ones.

## Prerequisites

Before you begin, gather the following information from your existing resources:

### For Azure Communication Services (ACS)
- **Resource ID**: Full Azure resource ID (format: `/subscriptions/{subscription-id}/resourceGroups/{rg-name}/providers/Microsoft.Communication/communicationServices/{acs-name}`)
- **Connection String**: Primary connection string from ACS resource

To get these values:
```bash
# Get ACS Resource ID
az communication list --query "[?name=='your-acs-name'].id" -o tsv

# Get ACS Connection String
az communication list-keys --name your-acs-name --resource-group your-rg --query primaryConnectionString -o tsv
```

### For AI Services (Azure OpenAI)
- **Resource ID**: Full Azure resource ID (format: `/subscriptions/{subscription-id}/resourceGroups/{rg-name}/providers/Microsoft.CognitiveServices/accounts/{ai-services-name}`)
- **Endpoint**: AI Services endpoint URL (format: `https://{resource-name}.cognitiveservices.azure.com/`)

To get these values:
```bash
# Get AI Services Resource ID
az cognitiveservices account show --name your-ai-services-name --resource-group your-rg --query id -o tsv

# Get AI Services Endpoint
az cognitiveservices account show --name your-ai-services-name --resource-group your-rg --query properties.endpoint -o tsv
```

## Configuration

### Option 1: Using `azd` environment variables

Set the following environment variables in your azd environment:

```bash
# For existing ACS
azd env set EXISTING_ACS_RESOURCE_ID "/subscriptions/.../communicationServices/your-acs"
azd env set EXISTING_ACS_CONNECTION_STRING "endpoint=https://...;accesskey=..."

# For existing AI Services
azd env set EXISTING_AI_SERVICES_RESOURCE_ID "/subscriptions/.../accounts/your-ai-services"
azd env set EXISTING_AI_SERVICES_ENDPOINT "https://your-ai-services.cognitiveservices.azure.com/"
```

Then update `infra/main.parameters.json` to read from environment variables:

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "environmentName": {
      "value": "${AZURE_ENV_NAME}"
    },
    "location": {
      "value": "${AZURE_LOCATION}"
    },
    "appExists": {
      "value": false
    },
    "existingAcsResourceId": {
      "value": "${EXISTING_ACS_RESOURCE_ID=}"
    },
    "existingAcsConnectionString": {
      "value": "${EXISTING_ACS_CONNECTION_STRING=}"
    },
    "existingAiServicesResourceId": {
      "value": "${EXISTING_AI_SERVICES_RESOURCE_ID=}"
    },
    "existingAiServicesEndpoint": {
      "value": "${EXISTING_AI_SERVICES_ENDPOINT=}"
    }
  }
}
```

### Option 2: Direct parameter file configuration

Edit `infra/main.parameters.json` and add the parameters directly:

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "environmentName": {
      "value": "${AZURE_ENV_NAME}"
    },
    "location": {
      "value": "${AZURE_LOCATION}"
    },
    "appExists": {
      "value": false
    },
    "existingAcsResourceId": {
      "value": "/subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.Communication/communicationServices/your-acs"
    },
    "existingAcsConnectionString": {
      "value": "endpoint=https://your-acs.communication.azure.com/;accesskey=xxx"
    },
    "existingAiServicesResourceId": {
      "value": "/subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.CognitiveServices/accounts/your-ai-services"
    },
    "existingAiServicesEndpoint": {
      "value": "https://your-ai-services.cognitiveservices.azure.com/"
    }
  }
}
```

## Deployment

Deploy using `azd up` as usual:

```bash
azd up
```

The deployment will:
- Skip creating ACS if `existingAcsResourceId` is provided
- Skip creating AI Services if `existingAiServicesResourceId` is provided
- Configure the application to use your existing resources
- Still create other required resources (Key Vault, Container App, etc.)

## Important Notes

1. **Permissions**: Ensure the managed identity created by this deployment has appropriate permissions on your existing resources:
   - For ACS: No specific RBAC required (uses connection string)
   - For AI Services: Requires `Cognitive Services OpenAI User` or `Cognitive Services OpenAI Contributor` role

2. **Model Deployment**: If using existing AI Services, ensure the model specified in `modelName` parameter (default: `gpt-4o-mini`) is already deployed in that resource.

3. **Location**: The existing AI Services resource must support Azure OpenAI Realtime API (currently `swedencentral` or `eastus2`).

4. **Partial Usage**: You can use an existing ACS resource while creating a new AI Services resource, or vice versa. Just provide parameters for the resource(s) you want to reuse.

## Troubleshooting

### Error: "Model deployment not found"
- Verify the model name matches a deployed model in your AI Services resource
- Check the model deployment name (not the base model name)

### Error: "Access denied to AI Services"
- Verify role assignments are correctly configured
- The managed identity needs appropriate permissions

### Error: "ACS connection failed"
- Verify the connection string is correct and not expired
- Check that the ACS resource is in an active state
