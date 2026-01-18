# LKE Cluster for BERT Model Inference
resource "linode_lke_cluster" "bert_inference" {
  label       = var.cluster_label
  k8s_version = var.k8s_version
  region      = var.region
  tags        = var.cluster_tags

  # CPU node pool for system workloads (ingress, monitoring, etc.)
  pool {
    type  = var.cpu_node_type
    count = var.cpu_node_count

    autoscaler {
      min = var.cpu_node_count
      max = var.cpu_node_count + 2
    }
  }

  # GPU node pool for BERT inference workloads
  pool {
    type  = var.gpu_node_type
    count = var.gpu_node_count

    autoscaler {
      min = var.gpu_node_count
      max = var.gpu_node_count + 2
    }
  }
}

# Save kubeconfig to local file for kubectl access
resource "local_file" "kubeconfig" {
  content         = base64decode(linode_lke_cluster.bert_inference.kubeconfig)
  filename        = "${path.module}/kubeconfig.yaml"
  file_permission = "0600"
}
