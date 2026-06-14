# Entity: Docker

The containerization engine — the unit of deployment across the course.

- A container runs a process on the host kernel with isolated resources → fast, portable, efficient, "runs anywhere" (vs. VMs).
- **Docker Compose** defines multi-container apps via YAML (used to run [[apache-kafka|Kafka]] locally).
- Foundation for [[kubernetes|Kubernetes]] orchestration and [[cloud-native-architecture|cloud-native]] CI/CD (Dockerfiles in the pipeline).
- In ML: multi-stage Dockerfile to train + serve a model behind a REST API ([[machine-learning-engineering]], [[ml-deployment-and-serving]]).

Appears in: [[cloud-native-applications]], [[machine-learning-engineering]], [[kafka-cheat-sheet]], [[syllabus]]
