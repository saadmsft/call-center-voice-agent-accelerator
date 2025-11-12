# Migration Summary: Container Apps → App Service

## Changes Made

### Infrastructure (Bicep)

#### Removed Modules
- ❌ `modules/containerregistry.bicep` - No longer needed
- ❌ `modules/containerapp.bicep` - Replaced with App Service
- ❌ `modules/fetch-container-image.bicep` - Container-specific

#### Added Modules
- ✅ `modules/appservice.bicep` - New App Service deployment
  - App Service Plan (Linux, Basic B1 tier)
  - App Service with Python 3.11 runtime
  - Hypercorn ASGI server configuration
  - Integrated with Key Vault for secrets
  - Log Analytics diagnostics

#### Updated Files
- `infra/main.bicep`
  - Removed Container Registry module reference
  - Replaced Container App with App Service module
  - Updated outputs (removed ACR, updated service endpoints)
  - Parameters: removed `useContainerRegistry`, kept `appExists` for future use

### Application Files

#### Added Files
- ✅ `server/requirements.txt` - Python dependencies for App Service deployment
- ✅ `server/startup.sh` - Optional startup script
- ✅ `docs/APP_SERVICE_DEPLOYMENT.md` - Comprehensive deployment guide

#### Updated Files
- `azure.yaml`
  - Changed host from `containerapp` to `appservice`
  - Removed Docker configuration
  - Updated pipeline variables

- `README.md`
  - Updated cost table (App Service instead of Container Apps/ACR)
  - Updated region requirements
  - Updated testing instructions
  - Added App Service deployment guide reference

### Key Configuration

#### App Service Settings (Auto-configured)
```
AZURE_VOICE_LIVE_ENDPOINT          → AI Services endpoint
VOICE_LIVE_MODEL                   → Model deployment name
ACS_CONNECTION_STRING              → Key Vault reference
AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID → Managed identity
PORT / WEBSITES_PORT               → 8000
```

#### Runtime Configuration
- **Platform**: Linux
- **Python Version**: 3.11
- **ASGI Server**: Hypercorn (4 workers)
- **Port**: 8000
- **Startup**: `hypercorn server:app --bind 0.0.0.0:8000 --workers 4`

## Benefits of App Service

1. **Simplified Deployment**
   - No Docker build required
   - Direct code deployment via `azd deploy`
   - Built-in Python runtime with Oryx build

2. **Cost Reduction**
   - No Container Registry costs (~$5-167/month saved)
   - Lower compute costs with Basic B1 tier (~$13/month vs ~$30/month)
   - Pay only for what you use

3. **Developer Experience**
   - Familiar Azure platform
   - Easy scaling (vertical and horizontal)
   - Built-in deployment slots
   - Native integration with Azure services

4. **Operations**
   - Built-in monitoring and diagnostics
   - Easy log streaming
   - Application Insights integration
   - Managed SSL certificates

## Deployment Commands

### Full Deployment
```bash
azd auth login
azd up
```

### Code Update Only
```bash
azd deploy
```

### Manual Deployment
```bash
cd server
zip -r app.zip .
az webapp deployment source config-zip \
  --resource-group <rg-name> \
  --name <app-name> \
  --src app.zip
```

## Migration Notes

### For Existing Deployments

If you already have this deployed with Container Apps:

1. **Clean Deployment** (Recommended):
   ```bash
   azd down --force --purge
   azd up
   ```

2. **Side-by-Side**:
   - Deploy with a new environment name
   - Test the App Service version
   - Switch DNS/configuration when ready
   - Delete old Container Apps deployment

### No Code Changes Required

The application code (`server/server.py`) remains unchanged:
- Same Quart framework
- Same endpoints
- Same WebSocket handling
- Same environment variable names

### Existing Resources

ACS, AI Services, Key Vault, and managed identity resources are reused:
- No changes to existing ACS configuration
- No changes to AI Services/models
- Same Key Vault secrets
- Same managed identity with same permissions

## Testing

After deployment:

1. **Web Client**: Navigate to `https://<app-service-name>.azurewebsites.net`
2. **ACS Webhook**: Use `https://<app-service-name>.azurewebsites.net/acs/incomingcall`
3. **Health Check**: All endpoints remain the same

## Troubleshooting

### Common Issues

1. **App won't start**
   - Check logs: `az webapp log tail --name <app-name> --resource-group <rg-name>`
   - Verify Python version and dependencies in requirements.txt

2. **Key Vault access denied**
   - Verify managed identity has "Key Vault Secrets User" role
   - Check Key Vault firewall settings

3. **Performance issues**
   - Scale up: Change SKU to S1 or P1v2 in appservice.bicep
   - Scale out: Add more instances via portal or CLI

## Cost Comparison

| Resource | Container Apps | App Service | Savings |
|----------|---------------|-------------|---------|
| Container Registry | ~$5-167/month | $0 | ~$5-167/month |
| Compute | ~$30/month | ~$13/month | ~$17/month |
| **Total Savings** | | | **~$22-184/month** |

*Basic tier pricing, actual costs may vary by region and usage*

## Documentation

- [App Service Deployment Guide](./APP_SERVICE_DEPLOYMENT.md)
- [Using Existing Resources](./USE_EXISTING_RESOURCES.md)
- [Azure App Service Docs](https://learn.microsoft.com/azure/app-service/)
