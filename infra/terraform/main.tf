resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

# --- Container registry (Basic SKU keeps idle storage cost minimal) ----------
resource "azurerm_container_registry" "this" {
  name                = var.acr_name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = var.tags
}

# --- AKS lab cluster ---------------------------------------------------------
resource "azurerm_kubernetes_cluster" "this" {
  name                = var.cluster_name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  dns_prefix          = var.cluster_name
  tags                = var.tags

  # Foundations for Workload Identity (steward auth) and KAITO (scale-to-zero GPU).
  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  # KAITO (AI toolchain operator) managed add-on. The azurerm provider (>= 4.x)
  # exposes this natively, so manage it here rather than via an out-of-band
  # `az aks update`. This is the target the hello-inference steward observes.
  ai_toolchain_operator_enabled = true

  default_node_pool {
    name           = "system"
    vm_size        = var.system_node_vm_size
    vnet_subnet_id = azurerm_subnet.aks.id

    # A single small node can't hold Langfuse (ClickHouse/Postgres/Redis/MinIO/
    # web/worker) + system pods + Defender + the KAITO controllers, which left
    # the KAITO Helm install stuck on "context deadline exceeded". Autoscale so
    # there is room, and scale back toward the floor when idle.
    auto_scaling_enabled = true
    min_count            = var.system_node_min_count
    max_count            = var.system_node_max_count

    # No GPU here — KAITO provisions the T4 spot node only when a Workspace needs it.
    node_labels = {
      "meshops.io/pool" = "system"
    }
    # Match the AKS default so it doesn't show as perpetual drift.
    upgrade_settings {
      max_surge = "10%"
    }
  }

  identity {
    type = "SystemAssigned"
  }

  # Managed Prometheus: emit metrics to the Azure Monitor Workspace via the DCR
  # association defined in monitoring.tf.
  monitor_metrics {}

  network_profile {
    network_plugin = "azure"
    network_policy = "azure"
    service_cidr   = var.aks_service_cidr
    dns_service_ip = var.aks_dns_service_ip
  }

  lifecycle {
    # Microsoft Defender for Containers is enabled by an org Azure Policy and
    # points at a Defender-managed Log Analytics workspace. Leave it alone so
    # Terraform neither disables it nor churns on the policy-injected drift.
    # The cluster autoscaler owns the node count, so ignore it too.
    ignore_changes = [
      microsoft_defender,
      default_node_pool[0].node_count,
    ]
  }
}

# --- Let the AKS kubelet pull from ACR ---------------------------------------
resource "azurerm_role_assignment" "kubelet_acrpull" {
  scope                            = azurerm_container_registry.this.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}
