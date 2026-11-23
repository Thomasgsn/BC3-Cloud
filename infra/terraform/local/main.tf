terraform { required_version = "= 1.17.2" }
# Provider terraform_data intégré : adaptateur CLI local explicite, pas un provider kind.
resource "terraform_data" "reproduction" {
  triggers_replace = [filesha256("../../../scripts/reproduce_local.sh")]
  provisioner "local-exec" {
    working_dir = "/workspace"
    command     = "bash scripts/reproduce_local.sh"
  }
}
output "scope" { value = "kind-rncp-bc3-repro-clean, kubeconfig BC3 dédié ; aucune ressource AWS" }
