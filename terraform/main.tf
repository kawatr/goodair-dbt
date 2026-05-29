# ============================================================
# GoodAir — Infrastructure as Code (Terraform)
# Recrée toute l'infrastructure Azure GoodAir
# Usage : terraform init && terraform apply
# ============================================================

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

# ── Variables ─────────────────────────────────────────────────────────────────
variable "location" {
  default = "francecentral"
}

variable "resource_group_name" {
  default = "goodair-rg"
}

variable "aqicn_token" {
  description = "Token API AQICN"
  sensitive   = true
}

variable "owm_api_key" {
  description = "Clé API OpenWeatherMap"
  sensitive   = true
}

variable "postgres_password" {
  description = "Mot de passe PostgreSQL"
  sensitive   = true
  default     = "GoodAir_Azure_2026!"
}

# ── Resource Group ────────────────────────────────────────────────────────────
resource "azurerm_resource_group" "goodair" {
  name     = var.resource_group_name
  location = var.location
}

# ── ADLS Gen2 — Data Lake ─────────────────────────────────────────────────────
resource "azurerm_storage_account" "goodair" {
  name                     = "goodair${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.goodair.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true  # ADLS Gen2
}

resource "random_string" "suffix" {
  length  = 5
  special = false
  upper   = false
}

# Conteneurs Bronze / Silver / Gold
resource "azurerm_storage_container" "bronze" {
  name                  = "bronze"
  storage_account_name  = azurerm_storage_account.goodair.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "silver" {
  name                  = "silver"
  storage_account_name  = azurerm_storage_account.goodair.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "gold" {
  name                  = "gold"
  storage_account_name  = azurerm_storage_account.goodair.name
  container_access_type = "private"
}

# ── PostgreSQL Flexible Server ────────────────────────────────────────────────
resource "azurerm_postgresql_flexible_server" "goodair" {
  name                   = "goodair-pg-${random_string.suffix.result}"
  resource_group_name    = azurerm_resource_group.goodair.name
  location               = var.location
  version                = "15"
  administrator_login    = "goodairadmin"
  administrator_password = var.postgres_password
  storage_mb             = 32768
  sku_name               = "B_Standard_B1ms"
  zone                   = "1"
}

resource "azurerm_postgresql_flexible_server_database" "goodairdb" {
  name      = "goodairdb"
  server_id = azurerm_postgresql_flexible_server.goodair.id
  collation = "en_US.utf8"
  charset   = "utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.goodair.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# ── Key Vault ─────────────────────────────────────────────────────────────────
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "goodair" {
  name                = "goodair-kv-${random_string.suffix.result}"
  location            = var.location
  resource_group_name = azurerm_resource_group.goodair.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = ["Get", "Set", "List", "Delete"]
  }
}

resource "azurerm_key_vault_secret" "aqicn_token" {
  name         = "AQICN-TOKEN"
  value        = var.aqicn_token
  key_vault_id = azurerm_key_vault.goodair.id
}

resource "azurerm_key_vault_secret" "owm_api_key" {
  name         = "OWM-API-KEY"
  value        = var.owm_api_key
  key_vault_id = azurerm_key_vault.goodair.id
}

resource "azurerm_key_vault_secret" "postgres_password" {
  name         = "POSTGRES-PASSWORD"
  value        = var.postgres_password
  key_vault_id = azurerm_key_vault.goodair.id
}

# ── Azure Functions — Extraction ──────────────────────────────────────────────
resource "azurerm_service_plan" "goodair" {
  name                = "goodair-plan"
  resource_group_name = azurerm_resource_group.goodair.name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "Y1"  # Consumption plan
}

resource "azurerm_linux_function_app" "extract" {
  name                = "goodair-extract-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.goodair.name
  location            = var.location

  storage_account_name       = azurerm_storage_account.goodair.name
  storage_account_access_key = azurerm_storage_account.goodair.primary_access_key
  service_plan_id            = azurerm_service_plan.goodair.id

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME          = "python"
    AQICN_TOKEN                       = var.aqicn_token
    OWM_API_KEY                       = var.owm_api_key
    AZURE_STORAGE_CONNECTION_STRING   = azurerm_storage_account.goodair.primary_connection_string
  }
}

resource "azurerm_linux_function_app" "transform" {
  name                = "goodair-transform-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.goodair.name
  location            = var.location

  storage_account_name       = azurerm_storage_account.goodair.name
  storage_account_access_key = azurerm_storage_account.goodair.primary_access_key
  service_plan_id            = azurerm_service_plan.goodair.id

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME          = "python"
    AZURE_STORAGE_CONNECTION_STRING   = azurerm_storage_account.goodair.primary_connection_string
    POSTGRES_HOST                     = azurerm_postgresql_flexible_server.goodair.fqdn
    POSTGRES_DB                       = "goodairdb"
    POSTGRES_USER                     = "goodairadmin"
    POSTGRES_PASSWORD                 = var.postgres_password
    POSTGRES_PORT                     = "5432"
  }
}

# ── Azure Data Factory ────────────────────────────────────────────────────────
resource "azurerm_data_factory" "goodair" {
  name                = "goodair-adf-${random_string.suffix.result}"
  location            = var.location
  resource_group_name = azurerm_resource_group.goodair.name
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "storage_account_name" {
  value = azurerm_storage_account.goodair.name
}

output "postgres_host" {
  value = azurerm_postgresql_flexible_server.goodair.fqdn
}

output "function_extract_url" {
  value = "https://${azurerm_linux_function_app.extract.default_hostname}"
}

output "function_transform_url" {
  value = "https://${azurerm_linux_function_app.transform.default_hostname}"
}

output "key_vault_name" {
  value = azurerm_key_vault.goodair.name
}
