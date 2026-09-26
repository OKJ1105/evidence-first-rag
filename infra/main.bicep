// `deploy-v0.1` Section 4.1: the provisioning definitions.
//
// Every resource the contract registers, inside the one resource group #205
// created, and nothing else: the container registry, the PostgreSQL Flexible
// Server, one Linux App Service plan, and the two apps `surface` and `relay`
// running one image. The Key Vault and the deploy identity already exist
// (#205) and are referenced, never created.
//
// Deployed by the deploy workflow alone (Section 4.2), which the owner starts
// by hand. No secret is a literal here: the server administrator's password
// arrives as a secure parameter read from Key Vault by the workflow, and each
// app reads its own secret through a Key Vault reference under its own
// identity (Section 4.3).

targetScope = 'resourceGroup'

@description('Deployment region. Defaults to the resource group\'s, Japan East for #205.')
param location string = resourceGroup().location

@description('The commit being deployed. It is the image tag: immutable, never `latest` (Section 4.1).')
@minLength(7)
param commit string

@description('The Key Vault #205 created. Referenced, never created.')
param keyVaultName string

@description('The deploy identity #205 created. Its principal receives AcrPush on the registry and nothing else here.')
param deployIdentityName string = 'id-efr-github-deploy'

@description('The server administrator login. Used by the deploy job only (Section 4.3).')
param administratorLogin string = 'efradmin'

@secure()
@description('The server administrator password, read from Key Vault by the deploy job. Never a literal.')
param adminSecret string

@description('The portfolio site\'s origin, or empty while it does not exist (Section 4.6). Never a wildcard.')
param corsOrigin string = ''

@description('The `relay-v0.1` Section 8.3 daily ceiling, or empty while none is registered: the relay then refuses every request.')
param relayDailyCeiling string = ''

// Section 4.3: the secrets each app reads, by name in the vault.
var surfaceVaultEntry = 'mvp-runtime-password'
var relayVaultEntry = 'anthropic-api-key'

// Built-in role definitions, by their fixed identifiers.
var roleAcrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var roleAcrPush = '8311e382-0749-4cb8-b61a-304f252e45ec'
var roleKeyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'

var suffix = uniqueString(resourceGroup().id)
var registryName = 'acrefr${suffix}'
var serverName = 'psql-efr-${suffix}'
var planName = 'plan-efr-${suffix}'
var surfaceName = 'app-efr-surface-${suffix}'
var relayName = 'app-efr-relay-${suffix}'
var surfaceHost = '${surfaceName}.azurewebsites.net'
var image = '${registry.properties.loginServer}/evidence-first-rag:${commit}'
var port = '8000'

// ---------------------------------------------------------------------------
// Referenced, not created (#205).
// ---------------------------------------------------------------------------

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource runtimePassword 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: vault
  name: surfaceVaultEntry
}

resource anthropicKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: vault
  name: relayVaultEntry
}

resource deployIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: deployIdentityName
}

// ---------------------------------------------------------------------------
// Section 4.1: the container registry. Basic, no admin user, no anonymous pull.
// ---------------------------------------------------------------------------

resource registry 'Microsoft.ContainerRegistry/registries@2025-04-01' = {
  name: registryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
  }
}

// Section 4.3: the deploy identity pushes, scoped to the registry.
resource deployPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, deployIdentity.id, roleAcrPush)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAcrPush)
    principalId: deployIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Section 4.1: PostgreSQL 17, the lowest Burstable compute, the smallest
// storage, no high availability, the minimum backup retention.
// ---------------------------------------------------------------------------

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: serverName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '17'
    administratorLogin: administratorLogin
    administratorLoginPassword: adminSecret
    storage: {
      storageSizeGB: 32
      autoGrow: 'Disabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

// Section 4.5: "allow Azure services" (#210, decided). The deploy job's runner
// is admitted by a rule the workflow adds and removes around its window.
resource allowAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: server
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ---------------------------------------------------------------------------
// Section 4.1: one Linux plan, the lowest tier that runs two always-on apps.
// ---------------------------------------------------------------------------

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  kind: 'linux'
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
}

// What both apps share: the image by its commit tag, pulled under the app's
// own identity (Section 4.1), HTTPS only (Section 4.5).
var commonSiteConfig = {
  linuxFxVersion: 'DOCKER|${image}'
  acrUseManagedIdentityCreds: true
  alwaysOn: true
  ftpsState: 'Disabled'
  minTlsVersion: '1.2'
  http20Enabled: true
}

// Section 4.6, `surface`'s column, and nothing else.
var surfaceSettings = concat(
  [
    { name: 'WEBSITES_PORT', value: port }
    { name: 'PGHOST', value: server.properties.fullyQualifiedDomainName }
    { name: 'PGPORT', value: '5432' }
    { name: 'MVP_DATABASE', value: 'mvp' }
    { name: 'PGSSLMODE', value: 'require' }
    {
      name: 'MVP_RUNTIME_PASSWORD'
      value: '@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=${surfaceVaultEntry})'
    }
    { name: 'EFR_MCP_ALLOWED_HOSTS', value: surfaceHost }
  ],
  empty(corsOrigin) ? [] : [{ name: 'EFR_CORS_ORIGIN', value: corsOrigin }]
)

// Section 4.6, `relay`'s column, and nothing else.
var relaySettings = concat(
  [
    { name: 'WEBSITES_PORT', value: port }
    {
      name: 'ANTHROPIC_API_KEY'
      value: '@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=${relayVaultEntry})'
    }
    { name: 'EFR_RELAY_MCP_URL', value: 'https://${surfaceHost}/mcp' }
  ],
  empty(relayDailyCeiling) ? [] : [{ name: 'EFR_RELAY_DAILY_CEILING', value: relayDailyCeiling }],
  empty(corsOrigin) ? [] : [{ name: 'EFR_CORS_ORIGIN', value: corsOrigin }]
)

resource surface 'Microsoft.Web/sites@2023-12-01' = {
  name: surfaceName
  location: location
  kind: 'app,linux,container'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    keyVaultReferenceIdentity: 'SystemAssigned'
    siteConfig: union(commonSiteConfig, {
      appCommandLine: 'uvicorn --factory evidence_first_rag.api.serve:build --host 0.0.0.0 --port ${port}'
      appSettings: surfaceSettings
    })
  }
}

resource relay 'Microsoft.Web/sites@2023-12-01' = {
  name: relayName
  location: location
  kind: 'app,linux,container'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    keyVaultReferenceIdentity: 'SystemAssigned'
    siteConfig: union(commonSiteConfig, {
      appCommandLine: 'uvicorn --factory evidence_first_rag.relay.serve:build --host 0.0.0.0 --port ${port}'
      appSettings: relaySettings
    })
  }
}

// Section 4.7: the platform's log store, 7 days.
resource surfaceLogs 'Microsoft.Web/sites/config@2023-12-01' = {
  parent: surface
  name: 'logs'
  properties: {
    applicationLogs: {
      fileSystem: {
        level: 'Information'
      }
    }
    httpLogs: {
      fileSystem: {
        enabled: true
        retentionInDays: 7
        retentionInMb: 35
      }
    }
  }
}

resource relayLogs 'Microsoft.Web/sites/config@2023-12-01' = {
  parent: relay
  name: 'logs'
  properties: {
    applicationLogs: {
      fileSystem: {
        level: 'Information'
      }
    }
    httpLogs: {
      fileSystem: {
        enabled: true
        retentionInDays: 7
        retentionInMb: 35
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Section 4.3: each app pulls the image, and reads only its own secret.
// ---------------------------------------------------------------------------

resource surfacePull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, surface.id, roleAcrPull)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAcrPull)
    principalId: surface.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource relayPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, relay.id, roleAcrPull)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAcrPull)
    principalId: relay.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Scoped to the one secret, not the vault: `surface` cannot read the
// Anthropic key, and `relay` cannot read the runtime password.
resource surfaceSecret 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(runtimePassword.id, surface.id, roleKeyVaultSecretsUser)
  scope: runtimePassword
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleKeyVaultSecretsUser)
    principalId: surface.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource relaySecret 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(anthropicKey.id, relay.id, roleKeyVaultSecretsUser)
  scope: anthropicKey
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleKeyVaultSecretsUser)
    principalId: relay.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output registryName string = registry.name
output registryLoginServer string = registry.properties.loginServer
output serverName string = server.name
output serverHost string = server.properties.fullyQualifiedDomainName
output surfaceName string = surface.name
output relayName string = relay.name
output surfaceHost string = surfaceHost
output relayHost string = '${relayName}.azurewebsites.net'
