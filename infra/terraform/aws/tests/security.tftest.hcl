# Provider simulé uniquement pour vérifier les contrats du plan ; aucun appel AWS.
mock_provider "aws" {}
variables {
  allow_cloud_creation = true
  bucket_name = "rncp-bc3-offline-test-unique"
  operator_role_arn = "arn:aws:iam::123456789012:role/operator"
  ci_role_arn = "arn:aws:iam::123456789012:role/ci"
  admin_cidrs = ["192.0.2.1/32"]
}
run "private_encrypted_resources" {
  command = plan
  assert {
    condition = aws_db_instance.database.storage_encrypted && !aws_db_instance.database.publicly_accessible && aws_db_instance.database.deletion_protection
    error_message = "RDS doit rester privé, chiffré et protégé."
  }
  assert {
    condition = aws_s3_bucket_public_access_block.private.block_public_policy && aws_s3_bucket_public_access_block.private.restrict_public_buckets
    error_message = "Le bucket doit être privé."
  }
  assert {
    condition = aws_s3_bucket_versioning.private.versioning_configuration[0].status == "Enabled"
    error_message = "La protection de versions doit être activée."
  }
  assert {
    condition = aws_eks_cluster.main.vpc_config[0].endpoint_private_access && length(aws_subnet.private) == 2
    error_message = "Le cluster doit avoir son accès privé et deux sous-réseaux privés."
  }
  assert {
    condition = alltrue([for rule in aws_s3_bucket_lifecycle_configuration.private.rule : rule.status == "Disabled"])
    error_message = "La purge ne doit jamais être activée sans accord sur la conservation."
  }
}
run "approved_retention_plan" {
  command = plan
  variables { enable_retention_policy = true }
  assert {
    condition = alltrue([for rule in aws_s3_bucket_lifecycle_configuration.private.rule : rule.status == "Enabled"])
    error_message = "L'activation explicite doit apparaître dans le plan, sans application AWS pendant ce test."
  }
}
