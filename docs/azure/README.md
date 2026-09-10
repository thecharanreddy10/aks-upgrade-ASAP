# AKS Upgrade Agent — Complete Azure Architecture and Deployment Guide

## Overview

This document repository contains implementation-accurate Azure architecture, deployment procedures, and operational guidance for the **AKS Upgrade Agent POC** — an AI-powered solution for safe, staged AKS cluster upgrades.

### What This Solution Does

The AKS Upgrade Agent is a **Foundry hosted agent** that:

1. **Assesses** AKS upgrade readiness (cluster/node health, pod health, PodDisruptionBudget constraints, storage health, deprecated APIs)
2. **Plans** staged upgrade paths (control-plane vs node-pool sequences)
3. **Requires** explicit human approval before any write operation
4. **Executes** approved upgrades asynchronously through MCP tools
5. **Monitors** upgrade progress and validates completion
6. **Remediates** identified blockers (PDB, pods, storage, deprecated APIs) with explicit approval

### Solution Architecture at a Glance

```
┌─────────────┐
│   End User  │
│  (Browser)  │
└──────┬──────┘
       │ Chat/Invoke
       ▼
┌──────────────────────────────────────┐
│  Azure AI Foundry Hosted Agent       │
│  ────────────────────────────────────│
│  • Foundry Agent Service             │
│  • gpt-5-mini (LLM deployment)       │
│  • Agent Framework (agent-framework) │
│  • Responses Protocol                │
└──────┬───────────────────────────────┘
       │ FoundryToolbox / MCP
       ▼
┌──────────────────────────────────────┐
│  Foundry Toolbox                     │
│  (Tool Discovery & Routing)          │
└──────┬───────────────────────────────┘
       │ MCP Streamable HTTP
       ▼
┌──────────────────────────────────────┐
│  AKS Operations MCP Server           │
│  ────────────────────────────────────│
│  • Azure Container Apps              │
│  • Python FastMCP                    │
│  • Azure SDK (ContainerServiceClient)│
│  • Kubernetes API (AKS Run Command)  │
└──────┬───────────────────────────────┘
       │ Azure Management APIs + Kubernetes
       ▼
┌──────────────────────────────────────┐
│  Target AKS Cluster                  │
│  (Customer's Infrastructure)         │
└──────────────────────────────────────┘
```

## Master Guides

**Start here**:
- **[MASTER-DEPLOYMENT-GUIDE.md](MASTER-DEPLOYMENT-GUIDE.md)** — Executive summary, quick-start navigation, role-based document access, validation checklist
- **[DOCUMENTATION_SCAFFOLDING.md](DOCUMENTATION_SCAFFOLDING.md)** — Templates for completing remaining 14 documents (06-19)

## Complete Document Structure

This guide is organized into 20 detailed sections covering every aspect of deployment and operations:

| # | Document | Status | Purpose |
|---|----------|--------|---------|
| 1 | [01-solution-overview.md](01-solution-overview.md) | ✓ Complete | Executive overview, components, problem statement |
| 2 | [02-component-inventory.md](02-component-inventory.md) | ✓ Complete | Complete component list with locations, technologies, dependencies |
| 3 | [03-azure-resource-inventory.md](03-azure-resource-inventory.md) | ✓ Complete | Every Azure resource required, why it's needed, how to configure it |
| 4 | [04-azure-architecture.md](04-azure-architecture.md) | ✓ Complete | Azure architecture diagram and resource layout |
| 5 | [05-agent-architecture.md](05-agent-architecture.md) | ✓ Complete | Agent design, tool orchestration, prompts, memory |
| 6 | [06-data-flow.md](06-data-flow.md) | Template | Complete data flow diagram, sequence, and per-connection details |
| 7 | [07-network-architecture.md](07-network-architecture.md) | Template | Networking, VNets, private endpoints, DNS, firewall |
| 8 | [08-security-and-identity.md](08-security-and-identity.md) | Template | Authentication, RBAC, managed identities, secrets, compliance |
| 9 | [09-prerequisites.md](09-prerequisites.md) | ✓ Complete | Environment requirements, tools, versions, permissions |
| 10 | [10-environment-configuration.md](10-environment-configuration.md) | Template | All environment variables, secrets, configuration sources |
| 11 | [11-azure-provisioning.md](11-azure-provisioning.md) | Template | Step-by-step Azure resource provisioning with commands |
| 12 | [12-application-deployment.md](12-application-deployment.md) | Template | Agent and MCP server deployment procedures |
| 13 | [13-cicd-deployment.md](13-cicd-deployment.md) | Template | CI/CD pipeline setup and deployment automation |
| 14 | [14-validation-and-smoke-tests.md](14-validation-and-smoke-tests.md) | Template | Post-deployment validation and smoke tests |
| 15 | [15-troubleshooting.md](15-troubleshooting.md) | Template | Troubleshooting matrix and diagnostics |
| 16 | [16-rollback.md](16-rollback.md) | Template | Rollback procedures for application and infrastructure |
| 17 | [17-operations-and-monitoring.md](17-operations-and-monitoring.md) | Template | Observability, logging, alerting, health checks |
| 18 | [18-cost-and-scaling.md](18-cost-and-scaling.md) | Template | Cost drivers, scaling configuration, optimization |
| 19 | [19-existing-environment-integration.md](19-existing-environment-integration.md) | Template | Reusing existing Azure resources, configuration changes |
| 20 | [20-complete-deployment-runbook.md](20-complete-deployment-runbook.md) | ✓ Complete | End-to-end executable deployment runbook |

## Quick Start for Deployments

### For Existing Azure Environments

If you already have an Azure environment:

1. Read **[09-prerequisites.md](09-prerequisites.md)** — verify CLI tools, permissions, resource providers
2. Read **[10-environment-configuration.md](10-environment-configuration.md)** — identify what configuration values you have vs. need
3. Read **[19-existing-environment-integration.md](19-existing-environment-integration.md)** — determine which existing resources to reuse
4. Follow **[20-complete-deployment-runbook.md](20-complete-deployment-runbook.md)** step-by-step
5. Execute **[14-validation-and-smoke-tests.md](14-validation-and-smoke-tests.md)** to validate

### For Brownfield Integration

If you're integrating into an existing AKS cluster:

1. Read **[07-network-architecture.md](07-network-architecture.md)** — ensure network connectivity to the target cluster
2. Read **[08-security-and-identity.md](08-security-and-identity.md)** — set up managed identity with appropriate RBAC roles
3. Read **[12-application-deployment.md](12-application-deployment.md)** — deploy agent and MCP server
4. Configure `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, and target cluster details in **[10-environment-configuration.md](10-environment-configuration.md)**
5. Test with a read-only assessment before enabling write gates

## Key Architecture Decisions

### 1. Foundry Hosted Agents
- **Why**: Managed containerization, built-in observability, integrated with Azure AI services
- **Impact**: No self-hosted agent infrastructure required; pay-per-invocation model

### 2. MCP over Foundry Toolbox
- **Why**: Standard tool discovery, vendor-neutral protocol, clean separation from agent
- **Impact**: MCP server can be deployed independently (Container Apps or Functions); can be reused by other agents

### 3. Asynchronous Upgrade Execution
- **Why**: AKS upgrades are long-running (10-30+ minutes); avoid blocking MCP requests
- **Impact**: Status polling required; agent must understand staged execution (control-plane → node-pools)

### 4. Explicit Write Gates
- **Why**: Safety-first approach; prevent accidental writes; audit trail
- **Impact**: `AKS_UPGRADE_ENABLE_WRITE` and `AKS_REMEDIATION_ENABLE_WRITE` must be explicitly enabled; all writes require explicit human approval

### 5. Distributed Identity
- **Why**: No shared secrets; use managed identities with RBAC; Workload Identity Federation for GitHub/DevOps
- **Impact**: Simplified secret rotation; enterprise-grade RBAC audit trail

## Critical Safety Features

1. **Explicit Human Approval** — Agent instructions mandate clear, unambiguous user approval before any write
2. **Write Gatekeeping** — Environment variables `AKS_UPGRADE_ENABLE_WRITE` and `AKS_REMEDIATION_ENABLE_WRITE` must be explicitly set
3. **Full Check Mode Enforcement** — Writes require `check_mode="full"` (prevents accidental `check_mode="quick"` writes)
4. **Scope Enforcement** — `control_plane_only` vs `complete_cluster` scope prevents unintended node-pool writes
5. **Readiness Validation** — Mandatory checks (node health, pod health, PDB, storage, deprecated APIs) must pass before upgrade
6. **Protected Namespaces** — `kube-system`, `kube-public`, `kube-node-lease`, `aks-command`, `gatekeeper-system`, `calico-system`, `tigera-operator` cannot be modified by remediation tools

## Getting Help

- **Architecture questions**: See [04-azure-architecture.md](04-azure-architecture.md) and [05-agent-architecture.md](05-agent-architecture.md)
- **Deployment issues**: See [20-complete-deployment-runbook.md](20-complete-deployment-runbook.md) and [15-troubleshooting.md](15-troubleshooting.md)
- **Integration questions**: See [19-existing-environment-integration.md](19-existing-environment-integration.md)
- **Security/identity questions**: See [08-security-and-identity.md](08-security-and-identity.md)
- **Cost concerns**: See [18-cost-and-scaling.md](18-cost-and-scaling.md)

---

**Last Updated**: 2026-09-10  
**Source Repository**: AISolutions-Virtusa/AKS-Upgrade-Agent (Azure DevOps)  
**Status**: Production POC
