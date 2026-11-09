# ADR-015 — ECS Fargate for the service, worker and agent sandboxes; one image with a production WSGI server

Status: accepted
Date: 2026-11-30
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ADR-007, ADR-008, CON-1, CON-2, CON-4, CON-6
Revisit when: Relay needs a workload that does not fit a container task (GPUs, long-lived connections at large scale); or the platform team offers a shared Kubernetes cluster with its own on-call; or idle task hours cost more than a scale-to-zero service would. Review by 2027-11-30 in any case.
Dependency: gunicorn
Supersedes: none.

## Context

ADR-007 chose one artifact with two process types. ADR-008 kept the HTTP service on the standard library and
said a production server would be a new dependency with its own ADR. The deployment needs a place to run the
service, the worker, the egress proxy (ADR-013) and on-demand agent sessions, each isolated from the others.

## Options considered

### Option A — ECS on Fargate: one task definition per process type, each with its own IAM role and security group

### Option B — EC2 instances in an Auto Scaling group, running the processes under systemd

### Option C — A managed Kubernetes cluster (EKS)

### Option D — Serverless functions for the service and the worker

## Decision

Option A. Each process type is a Fargate task with its own task role (database login, model access or nothing),
its own security group, no public IP, a read-only root filesystem, every Linux capability dropped, a numeric
non-root user and ECS Exec off. The service and worker share one image (`deploy/Containerfile`). The image runs the
unchanged WSGI application under gunicorn with two worker processes, through a new module,
`relay.service.wsgi`, which builds the app from environment variables and has no demo mode. gunicorn is installed
in the image only; nothing under `src/` imports it, so Relay's own `dependencies = []` and fitness rule AR5 hold.

At the price table's assumptions the three always-on services cost $43.25 a month, 19.5% of the fixed cost.

## Consequences

- No servers to patch; AWS runs the hosts. The team owns the image, its base and its dependency, which Chapter 13
  pins by digest, scans and signs.
- Two gunicorn processes per task means more than one process per service for the first time: the rate limit
  moves to the database in the same release (ADR-014).
- Isolation between tasks is the platform's; isolation between process types is the separate roles and groups.
- Fargate bills per second while a task runs, so idle non-production tasks cost money. Scaling the services to
  zero outside working hours is possible and is not yet done.

## Rejected alternatives

### Option B — EC2 instances in an Auto Scaling group, running the processes under systemd
Rejected because: operating-system patching, instance roles shared by every process on a host, and SSH access for debugging all land on one rota, for no capability the containers lack.
Revisit if: a workload needs hardware or kernel features Fargate does not offer.

### Option C — A managed Kubernetes cluster (EKS)
Rejected because: a cluster's control plane, upgrades, network plugin and admission policy are a second platform for four task types, which CON-1 cannot staff.
Revisit if: the organization runs a shared cluster with its own platform team and on-call, and Relay's workloads multiply.

### Option D — Serverless functions for the service and the worker
Rejected because: the worker holds leases and polls a queue, which suits a long-running process, and splitting the service into functions adds a second deployment model, as ADR-007 found for triage.
Revisit if: traffic becomes so uneven that idle tasks cost more than per-request billing, or the worker moves to an event-driven queue.
