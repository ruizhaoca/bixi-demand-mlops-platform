# Entity: Kubernetes

The de facto container orchestrator — the runtime substrate for [[cloud-native-architecture|cloud-native]] and ML serving.

- CNCF flagship (from Google's Borg). Manages container lifecycles: provisioning, scaling, availability, load balancing, health, self-healing.
- Glossary: pods (smallest compute unit), labels, replica sets, deployments, services, ingress. Portable across AWS/GCP/Azure/on-prem (avoids lock-in).
- Runs [[docker|Docker]] containers; orchestration patterns (sidecar/ambassador/adapter); service mesh (Istio) on top.
- **Kubeflow** runs ML workflows on K8s → bridges to [[ml-deployment-and-serving]] and [[mlops-lifecycle]].

Appears in: [[cloud-native-applications]], [[machine-learning-engineering]], [[real-world-ml-in-production]], [[syllabus]]
