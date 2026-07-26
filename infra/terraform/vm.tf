# --- Jumpbox: the only place you can reach the private Key Vault -------------
# You SSH here from WSL, then run `az keyvault secret set ...`. The vault's
# private endpoint resolves via the VNet-linked private DNS zone.

# Generated SSH keypair — private key written next to the Terraform state so WSL
# can use it immediately. Rotate/remove for anything beyond a lab.
resource "tls_private_key" "jumpbox" {
  count     = var.create_jumpbox ? 1 : 0
  algorithm = "ED25519"
}

resource "local_sensitive_file" "jumpbox_private_key" {
  count           = var.create_jumpbox ? 1 : 0
  content         = tls_private_key.jumpbox[0].private_key_openssh
  filename        = "${path.module}/jumpbox_id_ed25519"
  file_permission = "0600"
}

resource "azurerm_public_ip" "jumpbox" {
  count               = var.create_jumpbox ? 1 : 0
  name                = "pip-jumpbox-meshops"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

resource "azurerm_network_security_group" "jumpbox" {
  count               = var.create_jumpbox ? 1 : 0
  name                = "nsg-jumpbox-meshops"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = var.tags

  security_rule {
    name                       = "allow-ssh-from-operator"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefixes    = var.allowed_ssh_source_cidrs
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "deny-all-other-inbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "jumpbox" {
  count                     = var.create_jumpbox ? 1 : 0
  subnet_id                 = azurerm_subnet.jumpbox.id
  network_security_group_id = azurerm_network_security_group.jumpbox[0].id
}

resource "azurerm_network_interface" "jumpbox" {
  count               = var.create_jumpbox ? 1 : 0
  name                = "nic-jumpbox-meshops"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.jumpbox.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.jumpbox[0].id
  }
}

resource "azurerm_linux_virtual_machine" "jumpbox" {
  count               = var.create_jumpbox ? 1 : 0
  name                = "vm-jumpbox-meshops"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  size                = var.jumpbox_vm_size
  admin_username      = var.jumpbox_admin_username
  tags                = var.tags

  network_interface_ids = [azurerm_network_interface.jumpbox[0].id]

  admin_ssh_key {
    username   = var.jumpbox_admin_username
    public_key = tls_private_key.jumpbox[0].public_key_openssh
  }

  # Managed identity so you can `az login --identity` on the box and write secrets.
  identity {
    type = "SystemAssigned"
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  # Install Azure CLI so `az keyvault secret set` works out of the box.
  custom_data = base64encode(<<-CLOUDINIT
    #cloud-config
    package_update: true
    runcmd:
      - curl -sL https://aka.ms/InstallAzureCLIDeb | bash
  CLOUDINIT
  )
}

# The jumpbox identity may read/write Key Vault secrets.
resource "azurerm_role_assignment" "jumpbox_kv_secrets_officer" {
  count                = var.create_jumpbox ? 1 : 0
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = azurerm_linux_virtual_machine.jumpbox[0].identity[0].principal_id
}
