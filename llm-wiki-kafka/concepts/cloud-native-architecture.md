# Concept: Cloud-Native Architecture

How and where modern (ML) systems are built and run — the deployment substrate for everything in Modules III–IV.

## Definition
Cloud native = **container native**: API- and [[microservices|microservices]]-based, automated, DevOps-driven ("you build it, you run it"). Produces loosely coupled, resilient, observable systems.

## The stack
- **Containers** — [[docker|Docker]] (+ Compose); container vs. VM; registries.
- **Orchestration** — [[kubernetes|Kubernetes]] (CNCF flagship): pods, deployments, services, ingress; orchestration patterns (sidecar/ambassador/adapter).
- **Workflow** — Git + Gitflow, build servers, **CI/CD** pipelines.
- **Principles** — the **[[twelve-factor-app|12-Factor App]]**, FaaS/serverless, service mesh (Istio).

## Connections
- Rests on [[software-engineering-best-practices|SE discipline]] (CI, source control, decoupling).
- Motivates [[data-storage-and-formats|NoSQL/polyglot persistence]] (cloud-native needs horizontal scale).
- Feeds directly into [[ml-deployment-and-serving|ML deployment]] (containers for inference, Kubernetes for scaling, Kubeflow for ML on K8s) and [[mlops-lifecycle|MLOps]] (same CI/CD DNA).

Sources: [[cloud-native-applications]], [[software-engineering-best-practices]], [[nosql-big-data-files]], [[syllabus]]
