variable "linode_token" {
  description = "Linode API token"
  type        = string
  sensitive   = true
}

variable "cluster_label" {
  description = "Label for the LKE cluster"
  type        = string
  default     = "bert-inference-cluster"
}

variable "region" {
  description = "Linode region for the cluster"
  type        = string
  default     = "us-ord"
}

variable "k8s_version" {
  description = "Kubernetes version for LKE"
  type        = string
  default     = "1.33"
}

variable "gpu_node_type" {
  description = "Linode GPU instance type for inference nodes"
  type        = string
  default     = "g2-gpu-rtx4000a1-s"
}

variable "gpu_node_count" {
  description = "Number of GPU nodes in the pool"
  type        = number
  default     = 1
}

variable "cpu_node_type" {
  description = "Linode instance type for CPU-only nodes (for system workloads)"
  type        = string
  default     = "g6-standard-2"
}

variable "cpu_node_count" {
  description = "Number of CPU nodes in the pool"
  type        = number
  default     = 2
}

variable "cluster_tags" {
  description = "Tags to apply to the cluster"
  type        = list(string)
  default     = ["bert", "inference", "ml"]
}
