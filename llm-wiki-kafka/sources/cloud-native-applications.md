# Source: Cloud Native Applications

One-line: How modern apps are built and run on the cloud — XaaS, containers/Docker, Kubernetes orchestration, PaaS & Git workflow, CI/CD, the 12-Factor App, microservices/FaaS, service mesh (Istio), and Kubeflow.

Raw: `../markdown/CloudNativeApplicationArchitecture.md` (61 slides).

## Key takeaways
- **Cloud native = container native**; API- and [[microservices|microservices]]-based, automated, DevOps-driven ("you build it, you run it"). Loosely coupled, resilient, observable.
- **Infrastructure as Code** (Terraform, Juju, BOSH) on AWS/GCP/Azure.
- **Platform**: [[docker|containerization]] (Docker, Compose, container vs. VM), **container orchestration** via [[kubernetes|Kubernetes]] (CNCF flagship; pods, labels, replica sets, deployments, services, ingress), container registries.
- **PaaS / workflow**: Git + Gitflow, build servers; CI/CD pipeline (listen → build → test → deploy), Jenkinsfile + Dockerfiles example.
- **App architecture**: 10 attributes of cloud-native apps, [[microservices]], **FaaS / serverless**, the **[[twelve-factor-app|12-Factor App]]**, cloud-native design principles, container orchestration patterns (sidecar, ambassador, adapter).
- **Service mesh**: Istio (Envoy proxy, Mixer, Pilot, Citadel) for discovery, load balancing, mTLS, canary/A-B routing.
- **Kubeflow**: ML workflows on Kubernetes — bridges this deck to [[mlops-lifecycle]].

## Connects to
- Entities: [[docker]], [[kubernetes]], [[microservices]], [[twelve-factor-app]]
- Concepts: [[cloud-native-architecture]], [[ml-deployment-and-serving]], [[mlops-lifecycle]]
- Related sources: [[software-engineering-best-practices]], [[nosql-big-data-files]], [[machine-learning-engineering]]
