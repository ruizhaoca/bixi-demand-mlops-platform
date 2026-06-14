We are master's students at the Desautels Faculty of Management at McGill University.

Team (names + GitHub ids; personal contact details intentionally omitted from this public repo):

- Othmane Zizi — GitHub: othmane-zizi-pro
- Sarah Liu — GitHub: (to confirm)
- Ruihe Zhang (Louis) — GitHub: mudkipython
- Rui Zhao — GitHub: ruizhaoca

We must read the assignment instructions along with all the other files, i.e.:

- @instructions_final_project.md
- @instructions_final_project_presentation.md
- INSY684 Group Project (kept in the team's shared drive, not in this public repo)

The course materials are in:
- @llm-wiki-kafka

We must draw from them to ensure understanding and application of course concepts.

For the actual final project we produced a plan in the main directory:
- @plan.md

The plan includes:
- 1 phase per person,
- a general how-to on how to authenticate to GitHub from the coding agent,
- who handles what phase,
- each phase in a Pull Request on its own feature branch,
- a handoff prompt for the person whose turn it is to take on the next phase so they can just paste the prompt and the coding agent will know how and where to pick up from @plan.md.

This is the GitHub repo: https://github.com/ruizhaoca/bixi-demand-mlops-platform

We push the following to the remote repo:

- llm wiki folder (@llm-wiki-kafka)
- @plan.md
- CLAUDE.md (this file, redacted)
- @instructions_final_project.md
- @instructions_final_project_presentation.md

The plan is built to make extra sure (even if it means contradicting the individual plan files in the shared "INSY684 Group Project" folder) that this assignment gets a 100% grade and fulfills all requirements.

All production deployment is handled with CDK or Terraform (infrastructure as code) for AWS.

When everything is ready, deployment is run via the AWS CLI with the team's credentials against the CDK/Terraform code under `infra/` — see the Deployment Runbook (§8) in @plan.md.

If there is a report to produce, we produce it in LaTeX and convert it to PDF with tectonic.
