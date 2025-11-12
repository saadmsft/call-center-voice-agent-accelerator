# App Service Deployment Guide

This project now uses **Azure App Service** instead of Azure Container Apps and Azure Container Registry, simplifying deployment and reducing costs.

## Architecture Changes

- **Before**: Container Apps + Container Registry
- **After**: App Service (Linux with Python 3.11)

## Benefits

1. **Simpler Deployment**: Direct code deployment without Docker containers
2. **Lower Cost**: No Container Registry charges, lower App Service Plan costs
3. **Built-in Features**: Easy scaling, deployment slots, custom domains
4. **Native Python Support**: Built-in Python runtime with Oryx build

## Deployment Process

### 1. Standard Deployment

```bash
azd auth login
azd up
```

This will:
1. Create an App Service Plan (Basic B1 tier)
2. Create an App Service with Python 3.11 runtime
3. Deploy your code directly to the App Service
4. Configure environment variables automatically

### 2. Manual Deployment (Optional)

If you need to deploy manually after infrastructure is set up:

```bash
# Deploy code to App Service
azd deploy
```

Or using Azure CLI:

```bash
cd server
zip -r app.zip .
az webapp deployment source config-zip \
  --resource-group <your-rg> \
  --name <your-app-service-name> \
  --src app.zip
```

### 3. Local Development

Run locally using the same Quart application:

```bash
cd server
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .
python server.py
```

## Configuration

### App Service Settings

The following environment variables are automatically configured:

- `AZURE_VOICE_LIVE_ENDPOINT` - AI Services endpoint
- `VOICE_LIVE_MODEL` - Model deployment name (default: gpt-4o-mini)
- `ACS_CONNECTION_STRING` - From Key Vault reference
- `AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID` - Managed identity client ID
- `PORT` / `WEBSITES_PORT` - Port 8000

### Startup Command

The App Service uses Hypercorn as the ASGI server:

```bash
hypercorn server:app --bind 0.0.0.0:8000 --workers 4
```

## Scaling

### Vertical Scaling (Instance Size)

Change the App Service Plan SKU in `infra/modules/appservice.bicep`:

```bicep
sku: {
  name: 'B1'  // Options: B1, B2, B3, S1, S2, S3, P1v2, P2v2, P3v2
  tier: 'Basic'
  capacity: 1
}
```

### Horizontal Scaling (Instance Count)

Use Azure Portal or CLI:

```bash
az appservice plan update \
  --resource-group <your-rg> \
  --name <your-plan-name> \
  --number-of-workers 3
```

## Monitoring

Application logs are sent to Log Analytics workspace:

- HTTP Logs
- Console Logs  
- Application Logs
- Platform Logs

View logs in Azure Portal or using CLI:

```bash
az webapp log tail \
  --resource-group <your-rg> \
  --name <your-app-service-name>
```

## Troubleshooting

### Application Won't Start

1. Check logs: `az webapp log tail --name <app-name> --resource-group <rg-name>`
2. Verify Python version: Must be 3.11 or compatible with your dependencies
3. Check startup command in portal: App Service > Configuration > General Settings

### Key Vault Access Issues

Ensure the managed identity has "Key Vault Secrets User" role on the Key Vault.

### Performance Issues

1. Scale up to a higher tier (e.g., S1 or P1v2)
2. Enable Application Insights for detailed performance metrics
3. Consider enabling caching for static assets

## Cost Optimization

- **Development**: Use B1 tier (~$13/month)
- **Production**: Use S1 or P1v2 for better performance
- **Auto-scale**: Configure based on metrics to handle load

## Migration Notes

If migrating from the Container Apps version:

1. Existing ACS and AI Services resources remain unchanged
2. Remove Container Registry and Container Apps modules
3. App Service uses the same Key Vault secrets and managed identity
4. No changes required to application code
