terraform {
  required_version = ">= 1.8"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

provider "azurerm" {
  subscription_id = var.subscription_id
  features {
    key_vault {
      # Lab convenience: let `terraform destroy` remove the vault without a
      # manual purge wait. Soft-delete still applies at the Azure level.
      purge_soft_delete_on_destroy = true
    }
    resource_group {
      # AKS auto-creates subnet NSGs (…-nsg-<region>) that Terraform doesn't
      # manage. Without this, `terraform destroy` fails deleting the RG because
      # it "still contains resources". Let the RG delete clear those leftovers.
      prevent_deletion_if_contains_resources = false
    }
  }
}

provider "random" {}
