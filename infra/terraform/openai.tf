# --- Azure OpenAI: the steward's reasoning model -----------------------------
# The agent authenticates with Entra ID (Workload Identity in-cluster), so the
# account needs a custom subdomain and the steward identity needs the
# "Cognitive Services OpenAI User" data-plane role. No API keys are used.

resource "random_string" "aoai_suffix" {
  length  = 6
  special = false
  upper   = false
  numeric = true
}

resource "azurerm_cognitive_account" "openai" {
  name                  = "aoai-meshops-${random_string.aoai_suffix.result}"
  resource_group_name   = azurerm_resource_group.this.name
  location              = var.openai_location
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "aoai-meshops-${random_string.aoai_suffix.result}"
  tags                  = var.tags
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = var.openai_chat_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.openai_model_name
    version = var.openai_model_version
  }

  sku {
    name     = var.openai_deployment_sku_name
    capacity = var.openai_deployment_capacity
  }
}

# The steward (in-cluster, via Workload Identity) calls the model.
resource "azurerm_role_assignment" "steward_openai_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.hello_inference.principal_id
}

# The operator can call it too (e.g. running the agent locally after `az login`).
resource "azurerm_role_assignment" "operator_openai_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = data.azurerm_client_config.current.object_id
}
