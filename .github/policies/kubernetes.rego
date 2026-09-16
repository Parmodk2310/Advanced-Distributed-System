package phase7.kubernetes

deny[msg] {
  input.kind == "Service"
  input.spec.type == "LoadBalancer"
  msg := "committed Kubernetes manifests must remain private; public exposure is temporary and scripted"
}

deny[msg] {
  input.kind == "StatefulSet"
  not input.spec.template.spec.securityContext.runAsNonRoot
  msg := "StatefulSets must run as non-root"
}

deny[msg] {
  input.kind == "StatefulSet"
  input.spec.template.spec.automountServiceAccountToken == true
  msg := "StatefulSets must not automount service-account tokens"
}
