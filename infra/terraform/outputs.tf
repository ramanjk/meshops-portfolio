output "aks_resource_id" {
  description = "Full AKS resource ID — Helm env.aksResourceId."
  value       = azurerm_kubernetes_cluster.this.id
}

output "aks_oidc_issuer_url" {
  description = "OIDC issuer URL backing the federated credential."
  value       = azurerm_kubernetes_cluster.this.oidc_issuer_url
}

output "aks_kubelet_object_id" {
  description = "Kubelet identity object ID (already granted AcrPull in Terraform)."
  value       = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id
}

output "hello_inference_client_id" {
  description = "Workload-Identity client ID — Helm serviceAccount.clientId."
  value       = azurerm_user_assigned_identity.hello_inference.client_id
}

output "key_vault_name" {
  description = "Key Vault name — Helm keyVault.name."
  value       = azurerm_key_vault.this.name
}

output "key_vault_tenant_id" {
  description = "Key Vault tenant ID — Helm keyVault.tenantId."
  value       = azurerm_key_vault.this.tenant_id
}

output "amp_query_url" {
  description = "Managed Prometheus query endpoint — Helm env.azureMonitorWorkspaceQueryUrl."
  value       = azurerm_monitor_workspace.this.query_endpoint
}

output "acr_login_server" {
  description = "ACR login server for docker build/push."
  value       = azurerm_container_registry.this.login_server
}

output "grafana_endpoint" {
  description = "Managed Grafana URL for importing the dashboard."
  value       = azurerm_dashboard_grafana.this.endpoint
}

output "azure_openai_endpoint" {
  description = "Azure OpenAI endpoint — Helm env.azureOpenAiEndpoint."
  value       = azurerm_cognitive_account.openai.endpoint
}

output "azure_openai_chat_deployment_name" {
  description = "Deployment name — Helm env.azureOpenAiChatDeploymentName."
  value       = azurerm_cognitive_deployment.chat.name
}

output "jumpbox_public_ip" {
  description = "Public IP of the jumpbox (SSH target)."
  value       = var.create_jumpbox ? azurerm_public_ip.jumpbox[0].ip_address : null
}

output "jumpbox_ssh_command" {
  description = "Ready-to-run SSH command from WSL into the jumpbox."
  value = var.create_jumpbox ? format(
    "ssh -i %s/jumpbox_id_ed25519 %s@%s",
    path.module,
    var.jumpbox_admin_username,
    azurerm_public_ip.jumpbox[0].ip_address,
  ) : null
}

output "write_secrets_hint" {
  description = "On the jumpbox: authenticate as the VM identity, then set the Langfuse keys."
  value = var.create_jumpbox ? format(
    "az login --identity && az keyvault secret set --vault-name %s --name langfuse-public-key --value <pk> && az keyvault secret set --vault-name %s --name langfuse-secret-key --value <sk>",
    azurerm_key_vault.this.name,
    azurerm_key_vault.this.name,
  ) : null
}
