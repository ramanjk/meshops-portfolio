data "azurerm_client_config" "current" {}

resource "random_string" "kv_suffix" {
  length  = 6
  special = false
  upper   = false
  numeric = true
}

# Key Vault holds the Langfuse keys; the steward reads them via the CSI driver.
resource "azurerm_key_vault" "this" {
  name                       = "kv-meshops-${random_string.kv_suffix.result}"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = azurerm_resource_group.this.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  tags                       = var.tags

  # Private per policy: no public data-plane access. Reachable only via the
  # private endpoint below (AKS pods + jumpbox resolve it through private DNS).
  public_network_access_enabled = false

  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
  }
}

# Private endpoint that projects the vault into the VNet.
resource "azurerm_private_endpoint" "kv" {
  name                = "pe-kv-meshops"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  subnet_id           = azurerm_subnet.pe.id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-kv-meshops"
    private_connection_resource_id = azurerm_key_vault.this.id
    is_manual_connection           = false
    subresource_names              = ["vault"]
  }

  private_dns_zone_group {
    name                 = "kv-dns-zone-group"
    private_dns_zone_ids = [azurerm_private_dns_zone.kv.id]
  }
}

# Whoever runs terraform/az needs to write the Langfuse secrets post-provision.
resource "azurerm_role_assignment" "operator_kv_admin" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# The steward identity only needs to read secrets.
resource "azurerm_role_assignment" "steward_kv_secrets_user" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.hello_inference.principal_id
}

resource "azurerm_role_assignment" "steward_kv_reader" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.hello_inference.principal_id
}
