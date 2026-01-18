output "cluster_id" {
  description = "The ID of the LKE cluster"
  value       = linode_lke_cluster.bert_inference.id
}

output "cluster_label" {
  description = "The label of the LKE cluster"
  value       = linode_lke_cluster.bert_inference.label
}

output "cluster_status" {
  description = "The status of the LKE cluster"
  value       = linode_lke_cluster.bert_inference.status
}

output "api_endpoints" {
  description = "The API endpoints for the LKE cluster"
  value       = linode_lke_cluster.bert_inference.api_endpoints
}

output "kubeconfig_path" {
  description = "Path to the generated kubeconfig file"
  value       = local_file.kubeconfig.filename
}

output "pool_ids" {
  description = "The IDs of the node pools"
  value       = linode_lke_cluster.bert_inference.pool[*].id
}
