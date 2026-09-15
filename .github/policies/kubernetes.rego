package phase7.kubernetes

deny[msg] {
  input.kind == "StatefulSet"
  input.spec.template.spec.containers[_].securityContext.runAsNonRoot != true
  msg := "containers must run as non-root"
}

deny[msg] {
  input.kind == "Service"
  input.spec.type == "LoadBalancer"
  msg := "the committed release must remain private"
}
