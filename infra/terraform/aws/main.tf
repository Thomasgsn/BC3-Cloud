resource "aws_vpc" "main" {
  cidr_block           = "10.30.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
}
resource "aws_internet_gateway" "main" { vpc_id = aws_vpc.main.id }
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  availability_zone       = var.availability_zones[count.index]
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  map_public_ip_on_launch = false
  tags                    = { "kubernetes.io/role/elb" = "1" }
}
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  availability_zone = var.availability_zones[count.index]
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index + 10)
  tags              = { "kubernetes.io/role/internal-elb" = "1" }
}
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}
resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
resource "aws_eip" "nat" { domain = "vpc" }
resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.main]
}
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }
}
resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
resource "aws_kms_key" "data" {
  description             = "BC3 RDS S3 SQS et Secrets EKS"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}
resource "aws_cloudwatch_log_group" "eks" {
  name              = "/aws/eks/${var.name}/cluster"
  retention_in_days = 30
}
resource "aws_iam_role" "cluster" {
  name               = "${var.name}-cluster"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "eks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}
resource "aws_eks_cluster" "main" {
  name                      = var.name
  role_arn                  = aws_iam_role.cluster.arn
  version                   = var.eks_version
  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  access_config { authentication_mode = "API" }
  vpc_config {
    subnet_ids              = aws_subnet.private[*].id
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.admin_cidrs
  }
  encryption_config {
    resources = ["secrets"]
    provider { key_arn = aws_kms_key.data.arn }
  }
  depends_on = [aws_iam_role_policy_attachment.cluster, aws_cloudwatch_log_group.eks]
}
resource "aws_eks_access_entry" "operator" {
  for_each      = { operator = var.operator_role_arn, ci = var.ci_role_arn }
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = each.value
  type          = "STANDARD"
}
resource "aws_eks_access_policy_association" "operator" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = var.operator_role_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope { type = "cluster" }
  depends_on = [aws_eks_access_entry.operator]
}
resource "aws_eks_access_policy_association" "ci" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = var.ci_role_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"
  access_scope {
    type       = "namespace"
    namespaces = ["bc3-test"]
  }
  depends_on = [aws_eks_access_entry.operator]
}
resource "aws_iam_role" "nodes" {
  name               = "${var.name}-nodes"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "nodes" {
  for_each   = toset(["AmazonEKSWorkerNodePolicy", "AmazonEC2ContainerRegistryPullOnly", "AmazonEKS_CNI_Policy"])
  role       = aws_iam_role.nodes.name
  policy_arn = "arn:aws:iam::aws:policy/${each.value}"
}
resource "aws_launch_template" "nodes" {
  name_prefix = "${var.name}-nodes-"
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
}
resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "application"
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = aws_subnet.private[*].id
  instance_types  = ["t3.medium"]
  launch_template {
    id      = aws_launch_template.nodes.id
    version = tostring(aws_launch_template.nodes.latest_version)
  }
  scaling_config {
    desired_size = 2
    min_size     = 2
    max_size     = 3
  }
  update_config { max_unavailable = 1 }
  depends_on = [aws_iam_role_policy_attachment.nodes]
}
resource "aws_eks_addon" "pod_identity" {
  cluster_name = aws_eks_cluster.main.name
  addon_name   = "eks-pod-identity-agent"
  depends_on   = [aws_eks_node_group.main]
}
resource "aws_security_group" "database" {
  name        = "${var.name}-database"
  vpc_id      = aws_vpc.main.id
  description = "PostgreSQL depuis les noeuds EKS uniquement"
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_eks_cluster.main.vpc_config[0].cluster_security_group_id]
  }
}
resource "aws_db_subnet_group" "database" { subnet_ids = aws_subnet.private[*].id }
resource "aws_db_parameter_group" "database" {
  family = "postgres17"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}
resource "aws_db_instance" "database" {
  identifier                    = var.name
  engine                        = "postgres"
  engine_version                = "17"
  instance_class                = "db.t4g.micro"
  allocated_storage             = 20
  storage_type                  = "gp3"
  storage_encrypted             = true
  kms_key_id                    = aws_kms_key.data.arn
  db_name                       = "bc3"
  username                      = "bc3admin"
  manage_master_user_password   = true
  master_user_secret_kms_key_id = aws_kms_key.data.arn
  db_subnet_group_name          = aws_db_subnet_group.database.name
  vpc_security_group_ids        = [aws_security_group.database.id]
  parameter_group_name          = aws_db_parameter_group.database.name
  publicly_accessible           = false
  multi_az                      = true
  backup_retention_period       = 7
  deletion_protection           = true
  skip_final_snapshot           = false
  final_snapshot_identifier     = "${var.name}-final"
  auto_minor_version_upgrade    = true
}
resource "aws_s3_bucket" "private" { bucket = var.bucket_name }
resource "aws_s3_bucket_public_access_block" "private" {
  bucket                  = aws_s3_bucket.private.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "private" {
  bucket = aws_s3_bucket.private.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "private" {
  bucket = aws_s3_bucket.private.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data.arn
    }
    bucket_key_enabled = true
  }
}
resource "aws_s3_bucket_policy" "private" {
  bucket = aws_s3_bucket.private.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Sid = "DenyNonTLS", Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.private.arn, "${aws_s3_bucket.private.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
resource "aws_s3_bucket_lifecycle_configuration" "private" {
  bucket = aws_s3_bucket.private.id
  rule {
    id     = "backup-conservation-proposal"
    status = var.enable_retention_policy ? "Enabled" : "Disabled"
    filter { prefix = "backups/" }
    transition {
      days          = 30
      storage_class = "GLACIER_IR"
    }
    expiration { days = 180 }
    noncurrent_version_expiration { noncurrent_days = 30 }
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
  depends_on = [aws_s3_bucket_versioning.private]
}
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-dead-letter"
  kms_master_key_id         = aws_kms_key.data.arn
  message_retention_seconds = 1209600
}
resource "aws_sqs_queue" "jobs" {
  name                       = "${var.name}-jobs"
  kms_master_key_id          = aws_kms_key.data.arn
  visibility_timeout_seconds = 60
  receive_wait_time_seconds  = 10
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dlq.arn, maxReceiveCount = 3 })
}
resource "aws_iam_role" "application" {
  for_each           = toset(["api", "worker"])
  name               = "${var.name}-${each.key}"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "pods.eks.amazonaws.com" }, Action = ["sts:AssumeRole", "sts:TagSession"], Condition = { StringEquals = { "aws:RequestTag/kubernetes-namespace" = "bc3-test", "aws:RequestTag/kubernetes-service-account" = each.key } } }] })
}
resource "aws_iam_role_policy" "application" {
  for_each = aws_iam_role.application
  role     = each.value.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = each.key == "api" ? ["${aws_s3_bucket.private.arn}/attachments/*", "${aws_s3_bucket.private.arn}/exports/*"] : ["${aws_s3_bucket.private.arn}/exports/*"] },
    { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.private.arn}/${each.key == "api" ? "attachments" : "exports"}/*" },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.private.arn },
    { Effect = "Allow", Action = each.key == "api" ? ["sqs:SendMessage", "sqs:GetQueueUrl"] : ["sqs:SendMessage", "sqs:GetQueueUrl", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility"], Resource = aws_sqs_queue.jobs.arn },
    { Effect = "Allow", Action = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"], Resource = aws_kms_key.data.arn }
  ] })
}
resource "aws_iam_role_policy" "worker_deadletter" {
  role   = aws_iam_role.application["worker"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["sqs:SendMessage", "sqs:GetQueueUrl"], Resource = aws_sqs_queue.dlq.arn }] })
}
resource "aws_eks_pod_identity_association" "application" {
  for_each        = aws_iam_role.application
  cluster_name    = aws_eks_cluster.main.name
  namespace       = "bc3-test"
  service_account = each.key
  role_arn        = each.value.arn
  depends_on      = [aws_eks_addon.pod_identity]
}
resource "aws_ecr_repository" "application" {
  for_each             = toset(["api", "worker", "front"])
  name                 = "${var.name}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.data.arn
  }
}
output "cluster_name" { value = aws_eks_cluster.main.name }
output "database_host" { value = aws_db_instance.database.address }
output "bucket" { value = aws_s3_bucket.private.id }
output "queue_url" { value = aws_sqs_queue.jobs.url }
output "dlq_url" { value = aws_sqs_queue.dlq.url }
output "region" { value = var.region }
output "database_admin_secret_arn" { value = aws_db_instance.database.master_user_secret[0].secret_arn }
output "repositories" { value = { for k, v in aws_ecr_repository.application : k => v.repository_url } }
