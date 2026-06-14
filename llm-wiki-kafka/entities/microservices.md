# Entity: Microservices

An architectural style structuring an app as small, independent services — core to [[cloud-native-architecture]].

- Services are highly maintainable/testable, loosely coupled, **independently deployable**, organized around business capabilities, owned by small teams.
- Enable rapid, frequent, reliable delivery and tech-stack evolution.
- Drive **polyglot persistence** ([[data-storage-and-formats|NoSQL]] per service) and need a service mesh (Istio) for discovery/routing/mTLS.
- Contrast FaaS/serverless; both are cloud-native app patterns.

Appears in: [[cloud-native-applications]], [[nosql-big-data-files]]
