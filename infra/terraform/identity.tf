# User-assigned identity the steward federates to via Workload Identity.
resource "azurerm_user_assigned_identity" "hello_inference" {
  name                = var.identity_name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = var.tags
}

# Trust the in-cluster ServiceAccount (meshops/hello-inference) to mint tokens
# for this identity — no client secret ever leaves Azure.
resource "azurerm_federated_identity_credential" "hello_inference" {
  name                      = "fic-hello-inference"
  user_assigned_identity_id = azurerm_user_assigned_identity.hello_inference.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = azurerm_kubernetes_cluster.this.oidc_issuer_url
  subject                   = "system:serviceaccount:${var.steward_namespace}:${var.steward_service_account}"
}

# Read-only view of the AKS cluster (aks-mcp reads Workspace CRs and node state).
resource "azurerm_role_assignment" "steward_aks_reader" {
  scope                = azurerm_kubernetes_cluster.this.id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.hello_inference.principal_id
}

# Read cluster user credentials is not needed; the steward talks to the API via
# in-cluster ServiceAccount. Monitoring read on the AMW is granted in monitoring.tf.
