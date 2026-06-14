# Source: Software Engineering Best Practices

One-line: A condensed catalog of clean-code, SOLID, package, naming, testing, and pragmatic-programmer principles — the engineering discipline underneath everything else in the course.

Raw: `../markdown/Software Engineering Best Practices.md` (39 slides). From *Clean Code* (Martin), *Pragmatic Programmer* (Hunt/Thomas), *Code Complete* (McConnell).

## Key takeaways
- **General**: standard conventions, KISS, Boy Scout Rule, root-cause analysis; one-step build & test; source control + CI.
- **SOLID class design**: SRP, OCP, LSP, ISP, DIP. **Package principles**: cohesion (RREP, CCP, CRP), coupling (ADP, SDP, SAP).
- **Dependencies**: Law of Demeter (shy code); avoid singletons/service locators (use dependency injection); avoid feature envy, artificial/temporal coupling.
- **Naming & methods**: descriptive names, methods do one thing and descend one level of abstraction, few arguments, no flag arguments.
- **Don'ts**: duplication (DRY), magic numbers, dead code, exceptions for control flow, swallowing exceptions.
- **Pragmatic principles**: care about craft, don't live with broken windows, provide options not excuses, remember the big picture.
- **Testing aspects**: unit, integration, validation/verification, performance, usability, "testing the tests."

## Connects to
- Concepts: [[cloud-native-architecture]], [[mlops-lifecycle]], [[ml-testing-and-monitoring]]
- Related sources: [[cloud-native-applications]], [[real-world-ml-in-production]] (applies these to ML code/notebooks)
