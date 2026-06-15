---
name: terraform-k8s
description: Author and operate infrastructure-as-code with Terraform/OpenTofu and Kubernetes manifests — declarative provisioning, state management, modules, plan/apply discipline, and the K8s object model (Deployment/Service/Ingress, probes, requests/limits, HPA, ConfigMap/Secret, RBAC). Use when writing a Terraform module, structuring remote state and workspaces, debugging drift or a destructive plan, writing or reviewing K8s YAML/Helm/Kustomize, sizing requests/limits, or wiring probes. Boundary vs deployment-cicd — deployment-cicd owns the release process (CI pipeline, build/test stages, blue-green/canary/rolling rollout, version tagging, rollback playbook); this skill owns the substrate those releases deploy onto — declarative provisioning of cloud resources and the Kubernetes object definitions themselves. The pipeline runs apply; this skill is what those files contain. Defers image-build craft to docker and host-level tuning to linux-sysadmin.
tier: infra
domain: [infra]
last_reviewed: "2026-06-14"
---

# Terraform & Kubernetes — The Declarative Substrate

A practical guide to provisioning cloud infrastructure with Terraform/OpenTofu and defining workloads as Kubernetes objects, such that the system state lives in version control and a fresh environment is one `apply` away. Stack-agnostic across cloud providers; recipes target AWS/GCP/Azure providers and vanilla K8s + Helm/Kustomize.

## When to Use This Skill

- Writing or reviewing a Terraform/OpenTofu module — inputs, outputs, resource graph.
- Structuring remote state, workspaces/environments, and state locking before a team touches it.
- Reading a `terraform plan` that wants to destroy/recreate something and deciding if that is safe.
- Authoring K8s manifests (Deployment, Service, Ingress) or a Helm chart / Kustomize overlay.
- Sizing resource requests/limits, wiring liveness/readiness/startup probes, configuring an HPA.
- Managing config and secrets (ConfigMap, Secret, external secret operators) and RBAC.

Skip when: the question is *how releases ship* (pipeline stages, rollout strategy, versioning, rollback) — that is deployment-cicd. This skill is the infrastructure those releases land on.

## Terraform — State Is the Whole Game

Terraform's model: a `.tf` description of desired state, a state file recording what actually exists, and `plan`/`apply` reconciling the two. Everything hard about Terraform is about state.

- **Remote, locked state from day one.** Never a local `terraform.tfstate` for shared infra — two `apply`s race and corrupt it. Use an S3/GCS backend with DynamoDB/native locking. The state file contains secrets in plaintext → encrypt at rest, restrict access.
- **`plan` before every `apply`, read every line.** Especially `-/+ destroy and then create`: that recreates a resource (new DB, new IP, downtime). A force-new on an attribute you thought was mutable is the classic 2 a.m. outage.
- **Never edit the state file by hand.** Use `terraform state mv` / `import` / `rm`. Hand-editing JSON state desyncs it from reality.
- **Pin provider and module versions.** `~> 5.0`, not unconstrained — an unpinned provider upgrades mid-`apply` and changes resource behavior under you.
- **Drift is real.** Someone clicks in the console; `plan` now wants to "fix" it. Detect drift in CI (`plan` on a schedule, alert on non-empty diff); decide console-vs-code ownership per resource.

### Module structure

```hcl
# A module: a reusable unit with a typed interface. Not a dumping ground.
variable "environment" { type = string }
variable "instance_count" {
  type    = number
  default = 2
  validation {
    condition     = var.instance_count >= 1
    error_message = "instance_count must be at least 1."
  }
}
output "service_endpoint" { value = aws_lb.this.dns_name }
```

- One module = one cohesive concern (a VPC, a service, a database). Compose, don't nest deeply.
- Inputs typed and `validation`-guarded; outputs are the module's contract — downstream modules consume them, so treat output renames as breaking changes.
- Separate environments by **workspace or directory + tfvars**, not by copy-pasting modules. The module is the same; the inputs differ.

## Kubernetes — Declare the Desired State, Let the Controller Converge

K8s is a control loop: declare objects, controllers drive actual state toward them. Author the objects correctly and the platform self-heals.

### Deployment essentials — the four things people skip

| Field | Why it is mandatory | What breaks without it |
|---|---|---|
| **resource `requests`** | scheduler placement + QoS class | pods land on overloaded nodes; no Guaranteed QoS |
| **resource `limits`** | cap runaway containers | one container OOMs the node's neighbors |
| **`readinessProbe`** | gate traffic until the pod can serve | requests hit a pod still booting → 502s during deploy |
| **`livenessProbe`** | restart a wedged container | a deadlocked pod serves errors forever |

```yaml
resources:
  requests: { cpu: "100m", memory: "128Mi" }   # scheduler reserves this
  limits:   { cpu: "500m", memory: "256Mi" }   # hard cap; CPU throttles, memory OOM-kills
readinessProbe:
  httpGet: { path: /healthz, port: 8080 }
  initialDelaySeconds: 5
  periodSeconds: 10
livenessProbe:
  httpGet: { path: /livez, port: 8080 }
  initialDelaySeconds: 15
  periodSeconds: 20
```

- **Readiness ≠ liveness.** Readiness = "route traffic here?"; liveness = "kill and restart?". Conflating them (one `/health` doing both) causes restart storms when a dependency is briefly down — the pod should go *unready*, not get *killed*.
- **Set `requests` even if unsure.** Without them the scheduler treats the pod as zero-cost and bin-packs until the node falls over. Requests too high waste capacity; missing entirely is worse.
- **Memory limit hit = OOM-kill (hard); CPU limit hit = throttle (soft).** Size memory generously, CPU tightly.

### Config, secrets, scaling, access

- **ConfigMap** for non-secret config, **Secret** for credentials (base64 is *encoding*, not encryption — enable encryption-at-rest or an external secrets operator: External Secrets, Sealed Secrets, Vault).
- **HorizontalPodAutoscaler** scales replicas on a metric (CPU/memory/custom). Pair with sane `requests` — the HPA computes utilization against the request.
- **RBAC least-privilege.** Namespaced `Role` + `RoleBinding`, scoped ServiceAccounts. No `cluster-admin` for an app pod.
- **Templating: Helm vs Kustomize.** Helm for packaged, parameterized, redistributable charts; Kustomize for overlay-per-environment on plain manifests. Don't run both on the same object — pick one per surface.

## The Terraform ↔ K8s Seam

A common split: Terraform provisions the *cluster and cloud resources* (VPC, managed K8s control plane, managed DB, IAM, DNS); K8s manifests define the *workloads inside it*. Provisioning the cluster with Terraform and the in-cluster objects with GitOps (Argo CD / Flux) is the mainstream 2026 pattern — Terraform for the substrate, GitOps for what runs on it. Avoid managing fast-churning in-cluster objects through Terraform's slow plan/apply loop.

## Anti-Patterns (reject in review, fix on sight)

- **Local/unlocked Terraform state** for shared infra — corruption on concurrent apply.
- **Applying without reading the plan** — a silent destroy/recreate of a stateful resource.
- **Hand-editing the state file** — use `state mv`/`import`/`rm`.
- **Unpinned providers/modules** — non-reproducible builds, surprise behavior changes.
- **K8s Deployments with no requests/limits** — the node-killer.
- **One probe doing liveness + readiness** — restart storms on transient dependency blips.
- **Secrets as plain ConfigMaps / committed to git** — base64 is not encryption.
- **`:latest` image tags in manifests** — non-reproducible rollouts, broken rollback (defer image discipline to docker).
- **`cluster-admin` for application workloads** — blast radius of a compromised pod is the whole cluster.
- **Copy-pasted modules per environment** — drift between supposedly-identical envs; parameterize instead.

## Tools per surface (2026 defaults)

| Need | Default | Alternatives |
|---|---|---|
| IaC engine | OpenTofu / Terraform | Pulumi (general-purpose languages), CDK |
| State backend | S3 + DynamoDB lock / GCS / Terraform Cloud | Spacelift, env0 |
| K8s templating | Helm or Kustomize | jsonnet, cdk8s |
| In-cluster GitOps delivery | Argo CD / Flux | (pairs with deployment-cicd) |
| Policy / guardrails | OPA/Gatekeeper, Kyverno, `tflint`/`checkov` | Conftest |
| Secrets in K8s | External Secrets Operator, Sealed Secrets, Vault | cloud-native secret store CSI |

## Pairs With

- **deployment-cicd** — owns the release *process* (pipeline, rollout strategy, versioning, rollback) that *invokes* `terraform apply` / `kubectl apply`; this skill is the content of those files.
- **docker** — the image-build craft (multi-stage, minimal base, non-root) that produces what a K8s Deployment runs.
- **linux-sysadmin** — host/node-level tuning beneath the cluster.
- **observability** — `requests`/`limits` saturation, probe failures, and HPA decisions are golden signals; export them.
- **security-web** — RBAC, secrets handling, and supply-chain (image provenance) as the security overlay.

## See also

- Terraform / OpenTofu docs — backends, state, modules, `import`.
- Kubernetes docs — Configuration Best Practices; Pod resource management; probes.
- *Kubernetes Patterns* (Ibryam & Huß) — health probe, predictable demands, declarative deployment patterns.
- Argo CD / Flux docs — GitOps delivery into the cluster.
