# --- Azure Monitor Workspace (Managed Prometheus backend) --------------------
resource "azurerm_monitor_workspace" "this" {
  name                = var.monitor_workspace_name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = var.tags
}

# Data Collection Endpoint + Rule wire the AKS managed-Prometheus scrape into
# the Azure Monitor Workspace. This is what makes `monitor_metrics {}` land
# somewhere queryable.
resource "azurerm_monitor_data_collection_endpoint" "prom" {
  name                = "dce-meshops-prom"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  kind                = "Linux"
  tags                = var.tags
}

resource "azurerm_monitor_data_collection_rule" "prom" {
  name                        = "dcr-meshops-prom"
  resource_group_name         = azurerm_resource_group.this.name
  location                    = azurerm_resource_group.this.location
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.prom.id
  kind                        = "Linux"
  tags                        = var.tags

  destinations {
    monitor_account {
      monitor_account_id = azurerm_monitor_workspace.this.id
      name               = "MonitoringAccount1"
    }
  }

  data_flow {
    streams      = ["Microsoft-PrometheusMetrics"]
    destinations = ["MonitoringAccount1"]
  }

  data_sources {
    prometheus_forwarder {
      streams = ["Microsoft-PrometheusMetrics"]
      name    = "PrometheusDataSource"
    }
  }
}

resource "azurerm_monitor_data_collection_rule_association" "prom" {
  name                    = "dcra-meshops-prom"
  target_resource_id      = azurerm_kubernetes_cluster.this.id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.prom.id
}

# Let the steward identity query the managed-Prometheus endpoint (prom-mcp shim).
resource "azurerm_role_assignment" "steward_amw_data_reader" {
  scope                = azurerm_monitor_workspace.this.id
  role_definition_name = "Monitoring Data Reader"
  principal_id         = azurerm_user_assigned_identity.hello_inference.principal_id
}

# --- Azure Managed Grafana ---------------------------------------------------
resource "azurerm_dashboard_grafana" "this" {
  name                              = var.grafana_name
  resource_group_name               = azurerm_resource_group.this.name
  location                          = azurerm_resource_group.this.location
  grafana_major_version             = 11
  api_key_enabled                   = true
  deterministic_outbound_ip_enabled = false
  public_network_access_enabled     = true
  tags                              = var.tags

  identity {
    type = "SystemAssigned"
  }

  azure_monitor_workspace_integrations {
    resource_id = azurerm_monitor_workspace.this.id
  }
}

# Grafana's managed identity must be able to read metrics from the AMW.
resource "azurerm_role_assignment" "grafana_amw_data_reader" {
  scope                = azurerm_monitor_workspace.this.id
  role_definition_name = "Monitoring Data Reader"
  principal_id         = azurerm_dashboard_grafana.this.identity[0].principal_id
}

# Let the operator sign in to Grafana as an Admin.
resource "azurerm_role_assignment" "operator_grafana_admin" {
  scope                = azurerm_dashboard_grafana.this.id
  role_definition_name = "Grafana Admin"
  principal_id         = data.azurerm_client_config.current.object_id
}
