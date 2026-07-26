variable "subscription_id" {
  type        = string
  description = "Azure subscription ID to deploy the MeshOps sandbox into."
}

variable "resource_group_name" {
  type        = string
  description = "Sandbox resource group name."
  default     = "rg-meshops-sandbox"
}

variable "location" {
  type        = string
  description = "Azure region. Everything stays in one region to avoid egress cost. eastus2 had 0 T4 GPU quota; eastus had T4 quota but AKS control-plane capacity was exhausted (AKSCapacityHeavyUsage), so we use southcentralus which has T4=100 and available AKS capacity."
  default     = "southcentralus"
}

variable "cluster_name" {
  type        = string
  description = "AKS cluster name."
  default     = "aks-meshops-lab"
}

variable "system_node_vm_size" {
  type        = string
  description = "VM size for the system node pool (the always-on cost floor). Standard_D2as_v5 is not allowed in southcentralus for this subscription; Standard_D2as_v6 is (and is same 2 vCPU/8GB AMD class)."
  default     = "Standard_D2as_v6"
}

variable "system_node_min_count" {
  type        = number
  description = "Minimum nodes in the autoscaled system pool (the always-on floor). Must hold Langfuse + system + Defender + KAITO controllers."
  default     = 2
}

variable "system_node_max_count" {
  type        = number
  description = "Maximum nodes the system pool can scale out to (e.g. during KAITO install spikes or heavier demos)."
  default     = 10
}

variable "acr_name" {
  type        = string
  description = "Azure Container Registry name (globally unique, alphanumeric only)."
  default     = "acrmeshops"
}

variable "identity_name" {
  type        = string
  description = "User-assigned managed identity for the hello-inference steward."
  default     = "msi-hello-inference"
}

variable "monitor_workspace_name" {
  type        = string
  description = "Azure Monitor Workspace (Managed Prometheus) name."
  default     = "amw-meshops-lab"
}

variable "grafana_name" {
  type        = string
  description = "Azure Managed Grafana name."
  default     = "amg-meshops-lab"
}

variable "grafana_major_version" {
  type        = string
  description = "Managed Grafana major version. Standard SKU currently supports 12 or 13."
  default     = "12"
}

variable "steward_namespace" {
  type        = string
  description = "Kubernetes namespace the hello-inference steward runs in."
  default     = "meshops"
}

variable "steward_service_account" {
  type        = string
  description = "Kubernetes ServiceAccount name the steward uses (federated to the MSI)."
  default     = "hello-inference"
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to every resource for cost attribution."
  default = {
    project     = "meshops"
    iteration   = "iteration-01"
    environment = "lab"
    owner       = "ram"
  }
}

# --- Private networking / jumpbox -------------------------------------------
variable "vnet_address_space" {
  type        = list(string)
  description = "Address space for the lab VNet."
  default     = ["10.20.0.0/16"]
}

variable "aks_subnet_prefix" {
  type        = string
  description = "Subnet for AKS nodes/pods (Azure CNI)."
  default     = "10.20.0.0/20"
}

variable "pe_subnet_prefix" {
  type        = string
  description = "Subnet dedicated to private endpoints."
  default     = "10.20.16.0/24"
}

variable "jumpbox_subnet_prefix" {
  type        = string
  description = "Subnet for the jumpbox VM."
  default     = "10.20.17.0/24"
}

variable "aks_service_cidr" {
  type        = string
  description = "AKS service CIDR (must not overlap the VNet)."
  default     = "10.30.0.0/16"
}

variable "aks_dns_service_ip" {
  type        = string
  description = "AKS kube-dns service IP (inside aks_service_cidr)."
  default     = "10.30.0.10"
}

variable "create_jumpbox" {
  type        = bool
  description = "Create the Linux jumpbox VM used to reach the private Key Vault."
  default     = true
}

variable "jumpbox_vm_size" {
  type        = string
  description = "Jumpbox VM size (kept small; deallocate when idle). B-series (B2s/B2ms) hit capacity restrictions in southcentralus, so we use Standard_D2as_v6 (x86/AMD, 2 vCPU/8GB) which provisions there."
  default     = "Standard_D2as_v6"
}

variable "jumpbox_admin_username" {
  type        = string
  description = "Admin username on the jumpbox."
  default     = "azureuser"
}

variable "allowed_ssh_source_cidrs" {
  type        = list(string)
  description = "Source IP CIDRs allowed to SSH the jumpbox. This WSL box egresses through a rotating Microsoft NAT pool in 74.162.222.0/24 (observed .25/.28/.29/.32), so we allow that block rather than chase single IPs. Key-only auth keeps it safe enough for a lab jumpbox."
  default     = ["74.162.222.0/24"]
}

# --- Azure OpenAI ------------------------------------------------------------
variable "openai_location" {
  type        = string
  description = "Region for the Azure OpenAI account (gpt-4.1 availability varies by region). gpt-4.1 GlobalStandard confirmed available in southcentralus."
  default     = "southcentralus"
}

variable "openai_chat_deployment_name" {
  type        = string
  description = "Deployment name the steward calls (must match Helm env.azureOpenAiChatDeploymentName)."
  default     = "gpt-4.1"
}

variable "openai_model_name" {
  type        = string
  description = "Azure OpenAI model to deploy."
  default     = "gpt-4.1"
}

variable "openai_model_version" {
  type        = string
  description = "Model version for the deployment."
  default     = "2025-04-14"
}

variable "openai_deployment_sku_name" {
  type        = string
  description = "Deployment SKU (GlobalStandard has the widest gpt-4.1 availability)."
  default     = "GlobalStandard"
}

variable "openai_deployment_capacity" {
  type        = number
  description = "Deployment capacity in thousands of tokens/min (TPM). Small is plenty for the lab."
  default     = 10
}
