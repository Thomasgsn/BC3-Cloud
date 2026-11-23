terraform {
  required_version = "= 1.17.2"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.73.0" }
  }
}
provider "aws" {
  region = var.region
  default_tags { tags = { Project = "rncp-bc3", Owner = "Thomas-Gassmann", Environment = "test" } }
}
variable "allow_cloud_creation" {
  type    = bool
  default = false
  validation {
    condition     = var.allow_cloud_creation
    error_message = "Création cloud verrouillée : accord budget/droits requis avant de passer ce drapeau à true."
  }
}
variable "region" { default = "eu-west-3" }
variable "enable_retention_policy" {
  type        = bool
  default     = false
  description = "Activer la transition/purge S3 seulement après approbation réelle de la politique de conservation."
}
variable "name" { default = "rncp-bc3" }
variable "bucket_name" {
  type        = string
  description = "Nom S3 globalement unique, à choisir avant plan autorisé."
}
variable "availability_zones" {
  type    = list(string)
  default = ["eu-west-3a", "eu-west-3b"]
  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "Deux zones requises."
  }
}
variable "eks_version" { default = "1.35" }
variable "operator_role_arn" { type = string }
variable "ci_role_arn" { type = string }
variable "admin_cidrs" {
  type        = list(string)
  description = "CIDR de sortie de l’opérateur/runner CI dédié, jamais 0.0.0.0/0."
  validation {
    condition     = length(var.admin_cidrs) > 0 && !contains(var.admin_cidrs, "0.0.0.0/0")
    error_message = "Un accès API EKS borné est obligatoire."
  }
}
