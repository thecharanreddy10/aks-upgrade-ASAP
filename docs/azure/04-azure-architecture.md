# 04 — Azure Architecture

## Solution Architecture Diagram

### High-Level Architecture (Logical)

```mermaid
graph TB
    subgraph user["User Layer"]
        browser["🌐 Browser / Chat Interface"]
    end
    
    subgraph foundry["Azure AI Foundry"]
        agent["🤖 Hosted Agent\n(Foundry Agent Service)\nPython 3.13"]
        llm["🧠 LLM Deployment\n(gpt-5-mini)\nAzure OpenAI"]
        toolbox["🔧 Foundry Toolbox\n(MCP Discovery & Routing)"]
    end
    
    subgraph mcp["MCP Server Layer"]
        mcpserver["📋 AKS Operations MCP\n(Container Apps)\nPython 3.11, FastMCP"]
        tools["🛠️ Tools (29 total)\n• Discovery\n• Validation\n• Upgrade\n• Remediation"]
    end
    
    subgraph azure["Azure Management"]
        azsdk["Azure SDK Clients\n(ContainerServiceClient,\nRunCommandRequest)"]
        api["Azure Management APIs\n(AKS, ARM)"]
    end
    
    subgraph target["Target Infrastructure"]
        aks["☸️ Target AKS Cluster\n(Customer's)"]
        k8s["⚙️ Kubernetes API\n(via AKS Run Command)"]
    end
    
    browser -->|Chat/Invoke| agent
    agent -->|LLM Reasoning| llm
    agent -->|MCP Tool Discovery| toolbox
    toolbox -->|MCP Streamable HTTP| mcpserver
    mcpserver -->|Contains| tools
    tools -->|Azure SDK| azsdk
    azsdk -->|REST API| api
    api -->|Manage| aks
    tools -->|kubectl commands| k8s
    k8s -->|Control| aks
    
    style user fill:#e1f5ff
    style foundry fill:#fff3e0
    style mcp fill:#f3e5f5
    style azure fill:#e8f5e9
    style target fill:#fce4ec
```

### Detailed Component Architecture

```mermaid
graph LR
    subgraph sub["Azure Subscription (bb0e2c9e-d7fb-45e4-92cf-654f380e6388)"]
        subgraph rg["Resource Group"]
            
            subgraph ai["AI Services"]
                cog["Cognitive Services\n(cog-vtjc46vefyyj6)"]
                proj["Foundry Project\n(agent-framework-agent-...)"]
                openai["Azure OpenAI\n(gpt-5-mini)"]
            end
            
            subgraph compute["Compute & Hosting"]
                agent_container["Agent Container\n(Foundry Agent Service)"]
                mcp_container["MCP Container\n(Container Apps)"]
                acr["Container Registry\n(crccfxat3jn5lls)"]
            end
            
            subgraph identity["Identity"]
                agent_id["Managed Identity\n(Agent Runtime)"]
                mcp_id["Managed Identity\n(MCP Server)"]
            end
            
            subgraph observability["Observability"]
                logs["Log Analytics\nWorkspace"]
                appinsights["Application\nInsights"]
            end
            
        end
        
        subgraph target_scope["Target AKS Resources (in customer subscription/RG)"]
            target_aks["Target AKS Cluster\n(Customer-managed)"]
        end
    end
    
    cog -->|Contains| proj
    proj -->|Contains| openai
    openai -->|LLM Model| agent_container
    
    agent_container -->|Uses| agent_id
    agent_id -->|Access Token| openai
    
    agent_container -->|Pull Image| acr
    
    mcp_container -->|Pull Image| acr
    mcp_container -->|Uses| mcp_id
    mcp_id -->|Access Token| target_aks
    
    agent_container -->|MCP Calls| mcp_container
    
    mcp_container -->|Logs| logs
    agent_container -->|Traces| appinsights
    appinsights -->|Data To| logs
    
    mcp_id -->|Kubernetes API\nAKS Run Command| target_aks
    
    style sub fill:#e3f2fd
    style rg fill:#f5f5f5
    style ai fill:#fff3e0
    style compute fill:#e1f5ff
    style identity fill:#e8f5e9
    style observability fill:#f3e5f5
    style target_scope fill:#fce4ec
```

### Data Flow Diagram

```mermaid
sequenceDiagram
    actor User
    participant Browser as Browser / UI
    participant Agent as Foundry<br/>Agent Service
    participant LLM as Azure<br/>OpenAI
    participant Toolbox as Foundry<br/>Toolbox
    participant MCP as Container App<br/>AKS MCP Server
    participant SDK as Azure SDK
    participant AKSAPI as Azure<br/>Management APIs
    participant Target as Target<br/>AKS Cluster
    
    User->>Browser: "Can you upgrade my AKS cluster to 1.35.1?"
    Browser->>Agent: POST /api/agents/*/invoke (message)
    
    Agent->>Toolbox: FoundryToolbox.invoke (tool list)
    Toolbox-->>Agent: MCP tool schema
    
    Agent->>LLM: Prompt: "Plan assessment workflow"
    LLM-->>Agent: Response: "Call aks_get_cluster_details"
    
    Agent->>MCP: aks_get_cluster_details (subscription, rg, cluster)
    MCP->>SDK: ContainerServiceClient.managed_clusters.get()
    SDK->>AKSAPI: GET /subscriptions/.../managedClusters/cluster
    AKSAPI-->>SDK: Cluster metadata
    SDK-->>MCP: Cluster object
    MCP-->>Agent: {"kubernetes_version": "1.35.0", "provisioning_state": "Succeeded", ...}
    
    Agent->>LLM: Prompt: "Plan next check (node health)"
    LLM-->>Agent: Response: "Call aks_check_node_health"
    
    Agent->>MCP: aks_check_node_health (subscription, rg, cluster)
    MCP->>SDK: RunCommandRequest (kubectl get nodes)
    SDK->>AKSAPI: POST /subscriptions/.../runCommand
    AKSAPI->>Target: Execute AKS Run Command
    Target->>Target: kubectl get nodes -o json
    Target-->>AKSAPI: Node JSON
    AKSAPI-->>SDK: Command result
    SDK-->>MCP: Node status
    MCP-->>Agent: {"total_nodes": 3, "unhealthy_nodes": [...]}
    
    Agent->>LLM: Prompt: "Present plan to user"
    LLM-->>Agent: Response: "Render upgrade plan, ask for approval"
    
    Agent-->>Browser: "Ready to upgrade control plane to 1.35.1. Do you approve?"
    Browser-->>User: Display plan with approval button
    
    User->>Browser: "Yes, I approve the control-plane upgrade to 1.35.1"
    Browser->>Agent: POST /api/agents/*/invoke (approval message)
    
    Agent->>LLM: Prompt: "User approved. Call aks_execute_confirmed_upgrade"
    LLM-->>Agent: Response: "Call aks_execute_confirmed_upgrade(..., is_user_confirmed=True)"
    
    Agent->>MCP: aks_execute_confirmed_upgrade (subscription, rg, cluster, target_version, is_user_confirmed=True, confirmed_scope="complete_cluster")
    MCP->>MCP: Validate approval gates (write_enable, check_mode, scope)
    MCP->>SDK: ContainerServiceClient.managed_clusters.begin_create_or_update(ManagedCluster(...kubernetes_version="1.35.1"))
    SDK->>AKSAPI: PATCH /subscriptions/.../managedClusters/cluster
    AKSAPI-->>SDK: LRO Poller (status: Accepted)
    SDK-->>MCP: Poller returned
    MCP-->>Agent: {"status": "in_progress", "stage": "control_plane", "target": "1.35.1", "current": "1.35.0"}
    
    Agent-->>Browser: "Upgrade submitted. Polling status..."
    
    loop Status Polling (every 30 seconds)
        Agent->>MCP: aks_get_upgrade_execution_status (subscription, rg, cluster)
        MCP->>SDK: ContainerServiceClient.managed_clusters.get()
        SDK->>AKSAPI: GET /subscriptions/.../managedClusters/cluster
        AKSAPI-->>SDK: Cluster object (provisioning_state: "Upgrading")
        SDK-->>MCP: Cluster object
        MCP-->>Agent: {"cluster": {"kubernetes_version": "1.35.0", "provisioning_state": "Upgrading"}, ...}
        Agent-->>Browser: "Status: Upgrading... 45% complete"
    end
    
    par Upgrade In Progress
        Target->>Target: Control plane upgrade
    end
    
    Agent->>MCP: aks_get_upgrade_execution_status (subscription, rg, cluster)
    MCP->>SDK: ContainerServiceClient.managed_clusters.get()
    SDK->>AKSAPI: GET /subscriptions/.../managedClusters/cluster
    AKSAPI-->>SDK: Cluster object (kubernetes_version: "1.35.1", provisioning_state: "Succeeded")
    SDK-->>MCP: Cluster object
    MCP-->>Agent: {"cluster": {"kubernetes_version": "1.35.1", "provisioning_state": "Succeeded"}, ...}
    
    Agent->>LLM: Prompt: "Upgrade complete. Summarize result"
    LLM-->>Agent: Response: "Control plane successfully upgraded to 1.35.1"
    
    Agent-->>Browser: "✓ Control plane upgraded to 1.35.1. Upgrade complete."
    Browser-->>User: Display success message
```

### Network Architecture

```mermaid
graph TB
    subgraph internet["Internet"]
        user["End User"]
    end
    
    subgraph azure_cloud["Azure Region (eastus2)"]
        subgraph vnet["Virtual Network\n(if using private endpoints)"]
            subnet1["Container Apps Subnet"]
            subnet2["Private Endpoint Subnet"]
        end
        
        subgraph azure_services["Azure Managed Services"]
            agent_svc["Foundry Agent Service\n(Public or Private)"]
            container_apps["Container App\n(aks-mcp)"]
            cog_service["Cognitive Services\n(Public or Private)"]
            openai["Azure OpenAI\n(Public or Private)"]
        end
        
        subgraph app_services["Application Infrastructure"]
            acr["Container Registry\n(Private, ACR Pull)"]
            logs["Log Analytics"]
            appinsights["Application Insights"]
        end
    end
    
    subgraph customer_azure["Customer's Azure (Separate Subscription)"]
        customer_aks["Target AKS Cluster"]
        customer_vnet["Customer VNet\n(if private)"]
    end
    
    user -->|Browser: HTTPS| agent_svc
    agent_svc -->|SDK/HTTP: HTTPS| openai
    agent_svc -->|MCP: HTTPS| container_apps
    container_apps -->|SDK: HTTPS| cog_service
    container_apps -->|kubectl: AKS Run Command| customer_aks
    
    container_apps -->|Image Pull: HTTPS| acr
    agent_svc -->|Logs| logs
    agent_svc -->|Traces| appinsights
    container_apps -->|Logs| logs
    
    container_apps -.->|Private Endpoint\n(Optional)| cog_service
    agent_svc -.->|Private Endpoint\n(Optional)| openai
    
    style internet fill:#e0e0e0
    style azure_cloud fill:#e3f2fd
    style vnet fill:#f5f5f5
    style azure_services fill:#fff3e0
    style app_services fill:#f3e5f5
    style customer_azure fill:#fce4ec
```

### Deployment Architecture (azd + Foundry)

```mermaid
graph LR
    subgraph dev_local["Developer Workstation"]
        repo["Source Repository\n(GitHub/DevOps)"]
        azd["Azure Developer CLI\n(azd)"]
    end
    
    subgraph build["Build Pipeline\n(CI/CD)"]
        build_agent["Build Agent"]
        acr_build["ACR Build"]
    end
    
    subgraph infra["Infrastructure\n(azd provision)"]
        bicep["Bicep Templates\n(.azure/infra)"]
        rg["Resource Group\n(create/update)"]
    end
    
    subgraph deploy["Deployment\n(azd deploy)"]
        agent_deploy["Foundry Agent\nDeployment"]
        mcp_deploy["Container App\nDeployment"]
    end
    
    subgraph result["Deployed Solution"]
        foundry["Foundry Agent\nService"]
        ca["Container App\n(MCP)"]
        acr["Container\nRegistry"]
    end
    
    repo -->|git clone| azd
    azd -->|Build & Push| acr_build
    acr_build -->|Image| acr
    
    azd -->|azd provision| bicep
    bicep -->|Deploy| rg
    
    azd -->|azd deploy| agent_deploy
    azd -->|azd deploy| mcp_deploy
    
    agent_deploy -->|Image| foundry
    mcp_deploy -->|Image Pull| acr
    mcp_deploy -->|Deploy| ca
    
    foundry -->|Pull Image| acr
    
    style dev_local fill:#e1f5ff
    style build fill:#f3e5f5
    style infra fill:#e8f5e9
    style deploy fill:#fff3e0
    style result fill:#fce4ec
```

## Architecture Patterns

### Pattern 1: Asynchronous Upgrade Execution

```mermaid
sequenceDiagram
    Agent->>MCP: aks_execute_confirmed_upgrade(..., is_user_confirmed=True)
    MCP->>MCP: Validation gates
    MCP->>Azure: ARM API (LRO: Upgrade submission)
    Azure-->>MCP: LRO Poller (status: Accepted)
    MCP-->>Agent: Response: {"status": "in_progress"}
    
    Note over Agent,Azure: Request completes IMMEDIATELY<br/>Azure upgrade runs in background
    
    Agent->>MCP: aks_get_upgrade_execution_status()
    MCP->>Azure: ARM API (GET cluster)
    Azure-->>MCP: Cluster state (provisioning_state: "Upgrading")
    MCP-->>Agent: Response: {"status": "upgrading", "version": "1.35.0"}
    
    par Async Upgrade
        Azure->>Azure: Control plane upgrade (10-30 minutes)
    end
    
    Agent->>MCP: aks_get_upgrade_execution_status()
    MCP->>Azure: ARM API (GET cluster)
    Azure-->>MCP: Cluster state (provisioning_state: "Succeeded", version: "1.35.1")
    MCP-->>Agent: Response: {"status": "completed", "version": "1.35.1"}
```

### Pattern 2: Staged Node-Pool Upgrade (complete_cluster)

```mermaid
graph TD
    A["User Approves\ncomplete_cluster\nUpgrade to 1.35.1"]
    B["Execute Control Plane<br/>(confirmed_scope='complete_cluster')"]
    C["Poll Control Plane\nUntil Succeeded"]
    D{"Control Plane<br/>Reached 1.35.1?"}
    E["Refresh Node-Pool<br/>Upgrade Evidence"]
    F["Identify Eligible<br/>Node Pools<br/>(SUPPORTED only)"]
    G{"Node Pools<br/>Available?"}
    H["Execute Node Pool 1<br/>Upgrade"]
    I["Poll Node Pool 1"]
    J{"Node Pool 1<br/>Succeeded?"}
    K["Execute Node Pool 2<br/>Upgrade"]
    L["Poll Node Pool 2"]
    M{"Node Pool 2<br/>Succeeded?"}
    N["Final Verification"]
    O["Report Success"]
    P["Skip Node Pool<br/>(no SUPPORTED pools)"]
    
    A --> B
    B --> C
    C --> D
    D -->|No| C
    D -->|Yes| E
    E --> F
    F --> G
    G -->|No| P
    G -->|Yes| H
    H --> I
    I --> J
    J -->|No| I
    J -->|Yes| K
    K --> L
    L --> M
    M -->|No| L
    M -->|Yes| N
    P --> N
    N --> O
    
    style A fill:#fff3e0
    style B fill:#e1f5ff
    style E fill:#e8f5e9
    style O fill:#c8e6c9
```

### Pattern 3: Remediation with Explicit Approval

```mermaid
sequenceDiagram
    Agent->>MCP: aks_check_deprecated_apis(cluster, namespace)
    MCP-->>Agent: {"blockers": [{"pod": "gitrepo-test", "volume": "gitRepo"}]}
    Agent-->>User: "Found deprecated gitRepo volume. Can remediate?"
    
    User->>Agent: "Yes, fix it"
    
    Agent->>MCP: aks_remediate_deprecated_apis(..., dry_run=True)
    MCP-->>Agent: {"diff": "Replace gitRepo with git-sync pattern", "check_mode": "full"}
    Agent-->>User: "Here's what I'll change: [diff]. Approve?"
    
    User->>Agent: "Yes, apply the fix"
    
    Agent->>MCP: aks_remediate_deprecated_apis(..., dry_run=False, is_destructive=False)
    MCP->>MCP: Check write gates (AKS_REMEDIATION_ENABLE_WRITE=true)
    MCP->>Kubernetes: kubectl patch deployment...
    Kubernetes-->>MCP: Patch applied
    MCP-->>Agent: {"status": "success", "pod_replaced": true}
    
    Agent->>MCP: aks_validate_upgrade_readiness(...)
    MCP-->>Agent: {"readiness": {"is_ready": true}}
    Agent-->>User: "✓ Remediation complete. Cluster ready for upgrade."
```

## Security Boundaries

```mermaid
graph TB
    subgraph public["Public Internet"]
        user["End User"]
    end
    
    subgraph azure_boundary["Azure Subscription Boundary"]
        subgraph auth["Authentication & Authorization"]
            mi_agent["Agent Managed Identity"]
            mi_mcp["MCP Managed Identity"]
            rbac["RBAC Role Assignments"]
        end
        
        subgraph compute_layer["Compute Layer"]
            agent_container["Agent Container"]
            mcp_container["MCP Container"]
        end
        
        subgraph control["Access Control Gates"]
            write_gate1["is_user_confirmed=True"]
            write_gate2["AKS_UPGRADE_ENABLE_WRITE"]
            write_gate3["check_mode='full'"]
        end
    end
    
    subgraph customer_boundary["Customer Subscription\n(Target AKS)"]
        customer_aks["Target AKS Cluster"]
        k8s_rbac["Kubernetes RBAC"]
    end
    
    user -->|HTTPS| agent_container
    agent_container -->|Azure SDK| write_gate1
    agent_container -->|SDK| write_gate2
    agent_container -->|SDK| write_gate3
    
    agent_container -->|Uses| mi_agent
    mcp_container -->|Uses| mi_mcp
    
    mi_agent -->|RBAC| rbac
    mi_mcp -->|RBAC| rbac
    
    rbac -->|AKS Cluster User Role| customer_aks
    customer_aks -->|Kubernetes API| k8s_rbac
    
    style public fill:#e0e0e0
    style azure_boundary fill:#e3f2fd
    style auth fill:#fff3e0
    style compute_layer fill:#f3e5f5
    style control fill:#ffebee
    style customer_boundary fill:#fce4ec
```

## Multi-Region Considerations (Future)

For production deployments requiring multi-region capabilities:

```mermaid
graph TB
    subgraph region1["Primary Region (eastus2)"]
        agent1["Agent Service"]
        mcp1["MCP Server"]
        acr1["Container Registry"]
    end
    
    subgraph region2["Secondary Region (westus2)"]
        agent2["Agent Service"]
        mcp2["MCP Server"]
        acr2["Container Registry\n(Geo-Replicated)"]
    end
    
    subgraph global["Global/DNS"]
        traffic_mgr["Traffic Manager\nor Front Door"]
    end
    
    subgraph customers["Customer Resources\n(Multiple Subscriptions)"]
        aks1["AKS Cluster 1\n(Region A)"]
        aks2["AKS Cluster 2\n(Region B)"]
    end
    
    traffic_mgr -->|Route| agent1
    traffic_mgr -->|Route| agent2
    agent1 -->|Pull Image| acr1
    agent2 -->|Pull Image| acr2
    agent1 -->|MCP| mcp1
    agent2 -->|MCP| mcp2
    mcp1 -->|Manage| aks1
    mcp2 -->|Manage| aks2
    
    acr1 -.->|Geo-Replicate| acr2
    
    style region1 fill:#e1f5ff
    style region2 fill:#e8f5e9
    style global fill:#fff3e0
    style customers fill:#fce4ec
```

---

**Next**: [05-agent-architecture.md](05-agent-architecture.md) for agent design  
**Status**: Production POC  
**Last Updated**: 2026-09-10
