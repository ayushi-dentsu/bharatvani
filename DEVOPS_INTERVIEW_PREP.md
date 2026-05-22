# Lumen Conversational Navigation — DevOps & System Architecture Interview Prep

> **Purpose:** Quick-lookup reference for a 12-year experienced DevOps engineer to explain every architectural decision — the *what*, *why*, and *how* — during technical interviews.

---

## Table of Contents

1. [30-Second Elevator Pitch](#1-30-second-elevator-pitch)
2. [System Overview](#2-system-overview)
3. [Architecture Decisions — Why We Chose What We Chose](#3-architecture-decisions)
4. [Infrastructure Deep Dive](#4-infrastructure-deep-dive)
5. [Application Components](#5-application-components)
6. [Security Architecture](#6-security-architecture)
7. [Deployment Strategy](#7-deployment-strategy)
8. [Observability & Monitoring](#8-observability--monitoring)
9. [Networking & Connectivity](#9-networking--connectivity)
10. [Cost Engineering](#10-cost-engineering)
11. [Disaster Recovery & Reliability](#11-disaster-recovery--reliability)
12. [Interview Q&A — 50 Questions with Answers](#12-interview-qa)
13. [Quick Reference Cards](#13-quick-reference-cards)

---

## 1. 30-Second Elevator Pitch

> "I architected and operate a **production RAG (Retrieval-Augmented Generation) AI search platform** on Azure for Lumen Technologies. It enables conversational search on lumen.com — users ask natural language questions, we perform hybrid search (text + vector + semantic) across indexed web content, and stream AI-generated responses with source citations in real time.
>
> The stack is a **pnpm monorepo** with TypeScript and Python services, deployed via **Terraform** to Azure Container Apps, Azure Functions, and Azure Static Web Apps. All service-to-service auth uses **Managed Identities** — zero API keys in config. We use **Azure AI Search** for hybrid retrieval, **Azure OpenAI (GPT-5-mini)** for generation, and a **multi-agent framework** built on Microsoft MAF for extensibility."

---

## 2. System Overview

### What Does This System Do?

A conversational AI search platform that:
1. **Ingests** web content from lumen.com (via AEM publish events → Playwright scraping → HTML-to-Markdown conversion)
2. **Indexes** content with embeddings into Azure AI Search (hybrid text + vector index)
3. **Searches** using hybrid retrieval (BM25 keyword + cosine vector similarity + optional semantic reranking)
4. **Generates** AI responses with source citations via Azure OpenAI
5. **Streams** responses in real-time via SSE (Server-Sent Events)

### High-Level Data Flow

```
┌──────────────────── INGESTION PIPELINE ────────────────────┐
│                                                             │
│  AEM CMS ──publish event──▶ Storage Queue                  │
│                                  │                          │
│                                  ▼                          │
│  AEM Content Processor (Container App, Playwright)          │
│       │                                                     │
│       ▼                                                     │
│  Blob Storage (raw-content/html/)                           │
│       │ blob trigger                                        │
│       ▼                                                     │
│  Content Parser (Azure Function, TypeScript)                │
│       │                                                     │
│       ▼                                                     │
│  Blob Storage (markdown-content/) + Azure AI Search Index   │
└─────────────────────────────────────────────────────────────┘

┌──────────────────── QUERY PIPELINE ────────────────────────┐
│                                                             │
│  User ──HTTPS──▶ WAF ──▶ APIM (rate limit) ──▶ Query Orch  │
│                                                  │          │
│                              ┌────────────────────┤          │
│                              ▼                    ▼          │
│                     AI Content Safety     Azure AI Search    │
│                     PII Detection         (hybrid search)    │
│                              │                    │          │
│                              └────────┬───────────┘          │
│                                       ▼                      │
│                              Azure OpenAI (GPT-5-mini)       │
│                                       │                      │
│                                       ▼                      │
│                              SSE Stream ──▶ User             │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack at a Glance

| Layer | Technology | Why |
|-------|-----------|-----|
| **Monorepo** | pnpm workspaces | Shared types, single lockfile, efficient disk usage |
| **IaC** | Terraform (~4.54 azurerm) | Declarative, modular, state locking |
| **Compute** | Azure Container Apps | Serverless containers, SSE streaming, auto-scale |
| **Serverless** | Azure Functions (Flex Consumption) | Event-driven blob triggers, pay-per-execution |
| **AI/ML** | Azure OpenAI (GPT-5-mini, ada-002) | Enterprise-grade, managed identity support |
| **Search** | Azure AI Search (Standard) | Hybrid text+vector, built-in semantic ranking |
| **Database** | PostgreSQL Flexible Server v16 | Relational, Prisma ORM, flexible scaling |
| **Cache** | Azure Managed Redis | Query result caching, semantic cache |
| **API Gateway** | Azure API Management | Rate limiting, CORS, gateway secret validation |
| **Secrets** | Azure Key Vault | RBAC auth, purge protection, audit logging |
| **Monitoring** | Application Insights + Log Analytics | Distributed tracing, centralized logs |
| **Frontend** | Azure Static Web Apps | Free tier, global CDN, no server management |
| **Container Registry** | Azure Container Registry (Basic) | Managed identity pulls, geo-replicated in prod |

---

## 3. Architecture Decisions

### 3.1 Why RAG Over Fine-Tuning?

| Criteria | RAG (Our Choice) | Fine-Tuning |
|----------|------------------|-------------|
| **Content freshness** | ✅ Real-time (index updates immediately) | ❌ Requires retraining |
| **Cost** | ✅ Pay per query | ❌ Training costs ($$$) |
| **Hallucination control** | ✅ Grounded in retrieved documents | ⚠️ Can still hallucinate |
| **Source citations** | ✅ Natural — search results have URLs | ❌ No grounding |
| **Data privacy** | ✅ Content stays in our index | ⚠️ Content baked into model |

**Interview answer:** *"We chose RAG because lumen.com content changes frequently. RAG lets us update the search index within minutes of a CMS publish event, whereas fine-tuning would require expensive retraining cycles. RAG also gives us natural source citations since every response is grounded in retrieved documents."*

---

### 3.2 Why Azure Over AWS/GCP?

**Interview answer:** *"Lumen's enterprise runs on Azure — existing subscriptions, networking (DMZ/commercial VNet peering), compliance approvals, and WAF infrastructure were already in place. Azure AI Search provides a unique advantage: a single service that handles both text indexing AND vector storage, eliminating the need for a separate vector DB like Pinecone or Weaviate. Azure OpenAI also provides enterprise SLAs and data residency guarantees that consumer OpenAI API doesn't."*

**Key Azure-specific advantages we leverage:**
- Azure AI Search = text + vector + semantic in ONE service
- Managed Identity across all services (no API keys)
- VNet peering between DMZ and Commercial subscriptions
- Azure API Management Premium with VNet integration
- Azure AI Content Safety for prompt injection (Prompt Shield)

---

### 3.3 Why Monorepo with pnpm Workspaces?

```
dotcom-ai-assistant/
├── packages/
│   ├── aem-content-processor/    # TypeScript, Container App
│   ├── content-parser/           # TypeScript, Azure Function
│   ├── query-orchestrator/       # Python, Container App
│   ├── chat-ui/                  # Vanilla JS, Static Web App
│   ├── prisma-config/            # Database schema (shared)
│   ├── azure-services/           # Blob Storage utilities (shared)
│   ├── shared-types/             # TypeScript interfaces (shared)
│   └── shared-config/            # Config utilities (shared)
├── infra/                        # Terraform
├── scripts/                      # Deployment scripts
└── docs/                         # Documentation
```

**Why monorepo?**
- **Shared types** between content-parser and aem-content-processor (no version drift)
- **Single Prisma schema** used by 3 packages
- **Atomic commits** — change schema + parser + processor in one PR
- **pnpm specifically** — phantom dependency prevention, 60%+ disk savings via content-addressable store, strict workspace resolution

**Why NOT microservice repos?**
- Team is small (2-4 developers)
- Shared TypeScript types would require publishing npm packages
- Prisma schema changes would need coordinated releases

---

### 3.4 Why Container Apps Over Kubernetes?

| Criteria | Container Apps (Our Choice) | AKS (Kubernetes) |
|----------|---------------------------|-------------------|
| **Ops overhead** | ✅ Zero cluster management | ❌ Cluster upgrades, node pools |
| **Cost** | ✅ Consumption billing (scale to zero possible) | ❌ Node VMs always running |
| **Scaling** | ✅ Built-in KEDA-based auto-scaling | ✅ HPA/VPA but requires setup |
| **SSE streaming** | ✅ Native HTTP/2 support | ✅ Needs ingress config |
| **Learning curve** | ✅ Minimal for small team | ❌ Steep (RBAC, networking, storage) |
| **Managed Identity** | ✅ Built-in SystemAssigned | ✅ But needs AAD Pod Identity |

**Interview answer:** *"For a team of 2-4 developers deploying 2 container apps, AKS would be over-engineering. Container Apps gives us KEDA-based auto-scaling, built-in revision management, managed identity, and consumption billing — all without managing control plane upgrades or node pool sizing. If we hit Container Apps limits (like custom CNI or GPU workloads), we can migrate to AKS since the Docker images are the same."*

---

### 3.5 Why Azure Functions for Content Parser?

**Interview answer:** *"The content parser is triggered by blob uploads — a classic event-driven workload. Azure Functions gives us native blob trigger support, automatic scaling based on blob events, and consumption billing (we only pay when content is being processed). We don't need the parser running 24/7 like the query orchestrator."*

| Service | Query Orchestrator | Content Parser |
|---------|-------------------|----------------|
| **Pattern** | Long-running, always-on | Event-driven, sporadic |
| **Trigger** | HTTP (APIM) | Blob trigger |
| **Response** | SSE streaming (long-lived connections) | Fire-and-forget |
| **Runtime** | Python (FastAPI + MAF) | TypeScript (Azure Functions v4) |
| **Deployment** | Container App | Azure Functions (Flex Consumption) |
| **Billing** | Per replica/second | Per execution |

---

### 3.6 Why Python for Query Orchestrator (Not TypeScript)?

**Interview answer:** *"The Query Orchestrator uses Microsoft Agent Framework (MAF), which is Python-first. The AI/ML ecosystem — LangChain, semantic-kernel, agent-framework, azure-ai SDK — is richest in Python. FastAPI also provides excellent SSE streaming support via sse-starlette, interactive OpenAPI docs, and Pydantic validation that mirrors our guardrails schema."*

---

### 3.7 Why PostgreSQL Over Cosmos DB?

| Criteria | PostgreSQL (Our Choice) | Cosmos DB |
|----------|------------------------|-----------|
| **Schema** | ✅ Relational, Prisma ORM | ❌ Schema-less, harder to enforce |
| **Cost** | ✅ ~$25/month (Basic) | ❌ ~$50/month minimum (serverless) |
| **Queries** | ✅ Complex JOINs for analytics | ⚠️ Limited cross-partition queries |
| **ORM** | ✅ Prisma with migrations | ❌ No standard ORM |
| **pgvector** | ✅ Vector support if needed later | N/A |

**Interview answer:** *"Our data model is relational — pages, URL tracking, query logs, conversations — with foreign key relationships. PostgreSQL with Prisma gives us type-safe queries, automatic migrations, and a clear schema evolution path. We use pgvector-enabled PostgreSQL in local dev (docker-compose), which gives us the option to add vector operations at the database level later."*

---

### 3.8 Why Hybrid Search (Not Just Vector Search)?

**Interview answer:** *"Pure vector search struggles with specific product names, SKU numbers, and exact phrases. Pure keyword search misses semantic intent. Hybrid search combines BM25 keyword matching with cosine vector similarity, giving us the best of both worlds. Azure AI Search handles the score fusion internally using Reciprocal Rank Fusion (RRF). We can also layer on semantic reranking as an L2 pass."*

```
Search Pipeline:
  1. BM25 text search → top 50 keyword matches
  2. Vector search (1536-dim ada-002) → top 50 semantic matches  
  3. Score fusion (RRF) → combined ranking
  4. [Optional] Semantic reranking → L2 re-scoring with Microsoft's models
  5. Return top 10 to LLM for response generation
```

---

### 3.9 Why SSE (Server-Sent Events) Over WebSockets?

**Interview answer:** *"SSE is simpler for our use case — we have a unidirectional stream from server to client. WebSockets would add bidirectional complexity we don't need. SSE works over standard HTTP, passes through all proxies and load balancers without special configuration, and is natively supported by browsers. Azure API Management and Azure Container Apps both handle SSE without any special configuration."*

---

### 3.10 Why Microsoft Agent Framework (MAF)?

**Interview answer:** *"MAF gives us a standardized agent interface (ChatAgent + Tools), built-in Azure OpenAI integration with managed identity, and a graph-based workflow builder for future multi-agent scenarios. We implemented our RAG search as the first agent, but the architecture is ready for Calendly scheduling, form pre-population, and product comparison agents without refactoring."*

```python
# Agent interface — every future agent implements this
class BaseAgent(ABC):
    @property
    def agent_id(self) -> str: ...
    @property  
    def capability(self) -> AgentCapability: ...
    async def invoke(self, request: AgentRequest) -> AgentResponse: ...
    async def stream(self, request: AgentRequest) -> AsyncIterator[str]: ...
```

---

## 4. Infrastructure Deep Dive

### 4.1 Terraform Module Organization

```
infra/
├── modules/                    # 15 reusable modules (dev environment)
│   ├── shared/                 # Resource Group
│   ├── monitoring/             # Log Analytics + App Insights
│   ├── storage/                # Blob Storage + Queues
│   ├── ai-services/            # Azure OpenAI + Content Safety + Language
│   ├── search/                 # Azure AI Search + Index + Indexer + Skillset
│   ├── database/               # PostgreSQL Flexible Server
│   ├── key-vault/              # Azure Key Vault
│   ├── compute/                # Azure Functions (content-parser, index-orchestrator)
│   ├── container-apps/         # Container Apps + ACR
│   ├── api-gateway/            # API Management
│   ├── caching/                # Azure Managed Redis
│   ├── networking/             # VNet (minimal Phase 1, full Phase 2)
│   ├── role-assignments/       # All RBAC in one place
│   ├── static-web-app/         # Chat UI hosting
│   └── messaging/              # Event Hub (stub for Phase 2)
│
├── lumen-modules/              # Production-grade modules (nonprod/prod)
│   ├── networking/             # Full VNet with subnets
│   ├── private-endpoints/      # Private endpoints for all services
│   ├── container-apps/         # Production container configs
│   ├── compute/                # Production function configs
│   ├── api-gateway/            # Premium APIM with VNet integration
│   ├── container-registry/     # Premium ACR
│   ├── role-assignments/       # Production RBAC
│   └── storage/                # Production storage
│
├── environments/
│   ├── dev/                    # Development (public endpoints, basic SKUs)
│   ├── nonprod/                # Pre-production (private endpoints, VNet)
│   └── prod/                   # Production (private endpoints, premium SKUs)
│
├── config/                     # Shared naming, tags, networking locals
├── backend-bootstrap-{env}/    # Terraform state storage setup per env
├── scripts/                    # init.sh, plan.sh, apply.sh, destroy.sh
├── shared/                     # Cross-environment configs
└── validation/                 # Compliance policies and tests
```

**Why this structure?**
- **modules/** = dev-focused, simpler, public endpoints
- **lumen-modules/** = production-grade with VNet + private endpoints
- **Separate environments/** = each has own state file, own backend config
- **role-assignments as a dedicated module** = avoids circular dependencies (identity must exist before role can be assigned)

---

### 4.2 Terraform State Management

```
State Backend:
  ├── Azure Storage Account: connavtfstate
  ├── Container: tfstate
  ├── Locking: Azure blob leases (Cosmos DB for dev)
  ├── Encryption: Infrastructure encryption enabled
  ├── Versioning: Enabled
  └── Soft delete: Enabled

Per-environment state files:
  ├── dev.tfstate
  ├── nonprod.tfstate
  └── prod.tfstate
```

**Interview answer:** *"We use Azure Storage backend with blob lease locking. Each environment has its own state file to prevent cross-environment blast radius. State is encrypted at rest with infrastructure encryption. We bootstrap the state backend separately (backend-bootstrap/) so it's not managed by the same Terraform that uses it — avoiding the chicken-and-egg problem."*

**Backend bootstrap pattern:**
```bash
# One-time setup per environment
cd infra/backend-bootstrap-dev
./setup-backend.sh

# Then all subsequent operations use remote state
cd infra/environments/dev
terraform init -backend-config=backend.tfvars
```

---

### 4.3 Provider Configuration

```hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.54.0"   # Pessimistic constraint — allows patches only
    }
  }
}

provider "azurerm" {
  subscription_id = var.subscription_id
  features {
    resource_group {
      prevent_deletion_if_contains_resources = true  # Safety net
    }
    key_vault {
      purge_soft_delete_on_destroy    = false  # Security best practice
      recover_soft_deleted_key_vaults = true   # Prevent name collisions
    }
  }
}
```

**Why `~> 4.54.0`?**
*"Pessimistic version constraint allows patch updates (4.54.x) but blocks minor/major updates that could introduce breaking changes. We pin to a known-good minor version and upgrade deliberately."*

---

### 4.4 Tagging Strategy

```hcl
common_tags = {
  Environment = "dev"
  Project     = "Lumen Conversational Navigation"
  ManagedBy   = "Terraform"
  automation  = "expiry=never;workinghours=24x7"
  bpcid       = "US047"
  business    = "criticality=low;project=lumen-conversational-nav;financecontact=...;owner=...;brand=merkle"
  security    = "dataclassification=public;pii=no"
  technical   = "environment=development"
}
```

**Why structured tags?**
- **Cost allocation** — `bpcid` maps to business unit for chargeback
- **Security classification** — `dataclassification=public;pii=no` for compliance audits
- **Automation policies** — `expiry=never;workinghours=24x7` prevents auto-shutdown policies
- **Ownership** — `owner` and `financecontact` for accountability

---

### 4.5 Resource Naming Convention

```
Pattern: {type}-con-nav-{environment}

Examples:
  rg-con-nav-dev              # Resource Group
  ai-con-nav-dev              # Azure OpenAI
  search-con-nav-dev          # AI Search
  psql-con-nav-dev            # PostgreSQL
  kv-con-nav-dev              # Key Vault
  apim-con-nav-dev            # API Management
  log-con-nav-dev             # Log Analytics
  appi-con-nav-dev            # App Insights
  redis-con-nav-dev           # Redis
  func-parser-con-nav-dev     # Content Parser Function
  func-indexer-con-nav-dev    # Index Orchestrator Function

Storage (no hyphens allowed):
  connavdevstdec2025           # Content storage
  connavdevfuncdec2025         # Functions storage
  lumenconvnavdev              # Container Registry
```

---

### 4.6 Module Dependency Graph

```
shared (Resource Group)
  └──▶ monitoring (Log Analytics, App Insights)
        └──▶ storage (Blob, Queues)
        └──▶ ai_services (OpenAI, Content Safety, Language)
        └──▶ search (AI Search) ←── needs storage + ai_services
        └──▶ database (PostgreSQL)
        └──▶ key_vault ←── needs database (for connection string)
        └──▶ compute (Azure Functions) ←── needs storage + key_vault + monitoring
        └──▶ container_apps (Container Apps + ACR) ←── needs database + ai_services + monitoring
        └──▶ api_gateway (APIM) ←── needs container_apps + key_vault
        └──▶ static_web_app (Chat UI)
        └──▶ caching (Redis)
        └──▶ networking (VNet — minimal Phase 1)
        └──▶ role_assignments ←── needs ALL service principal IDs
```

**Why role_assignments is last:** *"RBAC role assignments require the principal_id of each managed identity, which is only available after the service is created. By putting all role assignments in a dedicated module that depends on everything else, we avoid circular dependencies and have a single place to audit all permissions."*

---

## 5. Application Components

### 5.1 AEM Content Processor

| Attribute | Value |
|-----------|-------|
| **Language** | TypeScript (Node.js) |
| **Deployment** | Azure Container App |
| **Base Image** | `mcr.microsoft.com/playwright:v1.57.0-jammy` |
| **Purpose** | Event-driven web scraping via Storage Queue |
| **CPU/Memory** | 1.0 CPU / 2Gi (Playwright needs memory) |
| **Replicas** | 1-1 (fixed, no auto-scaling) |
| **Auth** | SystemAssigned Managed Identity |

**How it works:**
1. AEM CMS publishes page → HTTPS event to APIM
2. APIM enqueues message to Azure Storage Queue
3. Container App polls queue, picks up message
4. Playwright scrapes the URL with headless Chromium
5. Raw HTML uploaded to Blob Storage (`raw-content/html/`)
6. Page status updated in PostgreSQL
7. Handles both publish AND unpublish events

**Why Playwright in a Container App?**
*"Playwright needs Chromium installed — this rules out Azure Functions (no browser support). Container Apps let us run the Playwright Docker image with sufficient memory (2Gi). The AEM processor is a background worker — no HTTP ingress needed."*

---

### 5.2 Content Parser

| Attribute | Value |
|-----------|-------|
| **Language** | TypeScript |
| **Deployment** | Azure Function (Flex Consumption, Y1 SKU) |
| **Trigger** | Blob trigger on `raw-content/html/{name}` |
| **Purpose** | HTML → Markdown conversion with metadata |
| **Build** | esbuild bundle (single file deployment) |
| **Auth** | Managed Identity for blob access (no connection strings) |

**How it works:**
1. Blob trigger fires when HTML appears in `raw-content/html/`
2. Parse HTML, strip nav/headers/footers/scripts
3. Convert to clean Markdown with frontmatter metadata
4. Write to `markdown-content/` container
5. Update page status in PostgreSQL via Prisma

**Deployment pattern (zip deploy):**
```bash
# esbuild bundles all dependencies into single file
pnpm run build:bundle
# Creates function.json for blob trigger
# Copies Prisma client binary
# Zip and deploy via az webapp deploy
az webapp deploy --src-path deploy.zip --type zip --async true
```

**Why esbuild?** *"Azure Functions on Linux requires a self-contained deployment. esbuild bundles all TypeScript + dependencies into a single index.js, except for native binaries like Prisma client which we copy separately. This gives us ~5MB deployment packages instead of ~200MB with node_modules."*

---

### 5.3 Query Orchestrator

| Attribute | Value |
|-----------|-------|
| **Language** | Python 3.11+ |
| **Framework** | FastAPI + Microsoft Agent Framework (MAF) |
| **Deployment** | Azure Container App |
| **CPU/Memory** | 0.5 CPU / 1Gi |
| **Replicas** | 1-3 (auto-scaling) |
| **Auth** | SystemAssigned Managed Identity |
| **Response** | SSE (Server-Sent Events) streaming |

**Module architecture:**
```
src/
├── main.py              # FastAPI app with lifespan
├── config.py            # Pydantic Settings (env vars)
├── agents/              # MAF ChatAgent implementations
│   ├── base.py          # Abstract BaseAgent
│   ├── rag_agent.py     # RAG search + generate
│   └── registry.py      # Agent discovery
├── tools/               # MAF-compatible tools
│   └── search.py        # Azure AI Search hybrid queries
├── orchestrator/        # Agent routing
│   ├── router.py        # Routes query → agent
│   └── workflow.py      # MAF workflow (future)
├── chat/                # HTTP endpoints
│   ├── router.py        # FastAPI routes
│   ├── service.py       # Business logic
│   ├── streaming.py     # SSE implementation
│   └── schemas.py       # Request/Response models
├── guardrails/          # Security pipeline
│   ├── validator.py     # Length check, sanitization
│   ├── content_safety.py # Prompt Shield (injection detection)
│   ├── pii_detection.py # PII detection (Azure AI Language)
│   ├── service.py       # Orchestrates all checks
│   └── dependencies.py  # FastAPI dependency injection
├── logging/             # Observability
│   ├── middleware.py     # Request/response logging
│   ├── sanitizer.py     # PII redaction in logs
│   ├── context.py       # Correlation ID propagation
│   ├── metrics.py       # Custom metrics
│   └── telemetry.py     # Application Insights
└── admin/               # Health endpoints
    ├── router.py        # /health, /ready, /status, /metrics
    └── schemas.py       # Response models
```

**Guardrails pipeline (executed on every request):**
```
Request
  │
  ▼
1. Query Length Validation ──── Max 2000 characters
  │
  ▼
2. Input Sanitization ──── Strip control chars, normalize whitespace
  │
  ▼
3. PII Detection ──── Azure AI Language (redact SSN, phone, email)
  │
  ▼
4. Prompt Injection Detection ──── Azure AI Content Safety (Prompt Shield)
  │
  ▼
Agent Processing (if all checks pass)
```

**Key endpoints:**
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/chat` | SSE streaming chat |
| `POST` | `/api/v1/chat/sync` | JSON response (non-streaming) |
| `GET` | `/api/v1/chat/agents` | List available agents |
| `GET` | `/health` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe (checks all dependencies) |
| `GET` | `/status` | Version, environment, config |
| `GET` | `/metrics` | Custom metrics |

---

### 5.4 Chat UI

| Attribute | Value |
|-----------|-------|
| **Technology** | HTML/CSS/JavaScript (no framework) |
| **Deployment** | Azure Static Web Apps (Free tier) |
| **Features** | SSE streaming, chat drawer, conversation history |
| **Storage** | localStorage (Phase 1), Cosmos DB (Phase 2) |

---

### 5.5 Azure AI Search Index

```
Index: rag-con-nav-dev
  Fields:
    ├── id (string, key)
    ├── content (string, searchable)
    ├── contentVector (Collection(Edm.Single), 1536 dimensions)
    ├── title (string, searchable, filterable)
    ├── url (string, filterable)
    ├── category (string, filterable, facetable)
    ├── lastModified (DateTimeOffset, sortable)
    └── chunkIndex (int32, sortable)

  Vector config:
    ├── Algorithm: HNSW (Hierarchical Navigable Small World)
    ├── Similarity: Cosine
    └── Dimensions: 1536 (text-embedding-ada-002)

  Integrated vectorization:
    ├── Skillset: text splitting (2000 char chunks, 500 overlap)
    ├── Embedding: Azure OpenAI ada-002 via skillset
    └── Indexer: scheduled every 30 minutes (PT30M)
```

---

## 6. Security Architecture

### 6.1 Zero-Trust Identity Model

**Core principle: NO API KEYS ANYWHERE**

All service-to-service authentication uses SystemAssigned Managed Identities with Azure RBAC.

```
┌─────────────────────────────────────────────────────────┐
│              RBAC Role Assignment Matrix                  │
├──────────────────────┬────────────────┬─────────────────┤
│ Principal            │ Target         │ Role            │
├──────────────────────┼────────────────┼─────────────────┤
│ Query Orchestrator   │ Azure OpenAI   │ Cognitive Svc   │
│                      │                │ OpenAI User     │
│ Query Orchestrator   │ AI Search      │ Search Index    │
│                      │                │ Data Reader     │
│ Query Orchestrator   │ Content Safety │ Cognitive Svc   │
│                      │                │ User            │
│ Query Orchestrator   │ AI Language    │ Cognitive Svc   │
│                      │                │ User            │
│ Query Orchestrator   │ Key Vault      │ KV Secrets User │
├──────────────────────┼────────────────┼─────────────────┤
│ Search Service       │ Blob Storage   │ Storage Blob    │
│                      │                │ Data Reader     │
│ Search Service       │ Azure OpenAI   │ Cognitive Svc   │
│                      │                │ OpenAI User     │
├──────────────────────┼────────────────┼─────────────────┤
│ Content Parser       │ Blob Storage   │ Storage Blob    │
│                      │                │ Data Contributor│
│ Content Parser       │ Key Vault      │ KV Secrets User │
├──────────────────────┼────────────────┼─────────────────┤
│ AEM Processor        │ Blob Storage   │ Storage Blob    │
│                      │                │ Data Contributor│
│ AEM Processor        │ Storage Queue  │ Storage Queue   │
│                      │                │ Data Contributor│
│ AEM Processor        │ Key Vault      │ KV Secrets User │
├──────────────────────┼────────────────┼─────────────────┤
│ Index Orchestrator   │ Azure OpenAI   │ Cognitive Svc   │
│                      │                │ OpenAI User     │
│ Index Orchestrator   │ AI Search      │ Search Service  │
│                      │                │ Contributor     │
│ Index Orchestrator   │ Blob Storage   │ Storage Blob    │
│                      │                │ Data Contributor│
├──────────────────────┼────────────────┼─────────────────┤
│ Container Apps (both)│ ACR            │ AcrPull         │
│ APIM                 │ Key Vault      │ KV Secrets User │
└──────────────────────┴────────────────┴─────────────────┘
```

**Interview answer:** *"Every service uses SystemAssigned Managed Identity. The identity is created automatically by Azure when we deploy the resource, and we assign RBAC roles via a dedicated Terraform module. This means: no API keys to rotate, no secrets to leak, no credential management overhead. The only secrets in Key Vault are the database password and gateway secret — both created by Terraform and consumed via Key Vault references."*

---

### 6.2 Gateway Secret Pattern

```
APIM → [injects X-Gateway-Secret header] → Container App → [validates header]

Purpose: Prevent direct access to Container App bypassing APIM rate limits
```

```hcl
# Terraform: APIM reads secret from Key Vault via Named Value
gateway_secret_secret_uri = module.key_vault.gateway_secret_secret_uri

# Container App validates:
# GATEWAY_SECRET env var (from secret)
# ENFORCE_GATEWAY_VALIDATION = true
```

**Interview answer:** *"The Container App has a public FQDN (Azure requirement for Container Apps with external ingress). To prevent users from bypassing APIM's rate limiting, APIM injects an X-Gateway-Secret header on every request. The Query Orchestrator validates this header and rejects direct access when ENFORCE_GATEWAY_VALIDATION is true."*

---

### 6.3 Key Vault Integration Pattern

```hcl
# Key Vault stores 3 secrets:
# 1. db-admin-password    — PostgreSQL admin password
# 2. database-url         — Full connection string
# 3. gateway-secret       — APIM validation secret

# Services consume via:
# Option A: Key Vault Reference (Azure Functions)
"DATABASE_URL" = "@Microsoft.KeyVault(SecretUri=${module.key_vault.database_url_secret_uri})"

# Option B: Direct secret injection (Container Apps)
secret {
  name  = "database-url"
  value = var.database_url
}
```

**Why two patterns?** *"Azure Functions natively support Key Vault references — the runtime resolves the secret at startup. Container Apps don't support Key Vault references yet, so we inject the secret value directly via Terraform. Both patterns avoid hardcoding secrets in application config."*

---

### 6.4 Content Safety Guardrails

| Check | Azure Service | What It Catches |
|-------|--------------|-----------------|
| **Prompt injection** | AI Content Safety (Prompt Shield) | "Ignore instructions and..." |
| **PII detection** | AI Language (TextAnalytics) | SSN, phone, email, credit card |
| **Input validation** | Custom (Python) | SQL injection, XSS, oversized queries |
| **Content moderation** | AI Content Safety | Hate, violence, self-harm, sexual content |

**Interview answer:** *"We run a multi-layer guardrails pipeline on every user query BEFORE it reaches the LLM. Azure AI Content Safety's Prompt Shield detects prompt injection attacks. Azure AI Language detects PII and redacts it. Our custom validator handles length limits, control character stripping, and input sanitization. If any check fails, we return a safe error response without calling the LLM."*

---

### 6.5 Security Posture Summary

| ✅ In Place | ❌ Not Yet (Planned) |
|------------|---------------------|
| Managed Identity everywhere | Private endpoints (Phase 2) |
| TLS 1.2+ enforced | VNet integration for Functions |
| Encryption at rest (Azure-managed keys) | Network Security Groups |
| Gateway secret validation | APIM subscription keys |
| Rate limiting (IP-based, 10 req/min chat) | OAuth/Azure AD authentication |
| Prompt injection detection | CMK (Customer-Managed Keys) |
| PII detection and redaction | |
| Key Vault with purge protection | |
| Blob versioning + soft delete | |
| Non-root container user | |

---

## 7. Deployment Strategy

### 7.1 Deployment Overview

| Component | Method | Target | CI/CD |
|-----------|--------|--------|-------|
| **Infrastructure** | Terraform CLI | Azure | Manual (scripts/) |
| **Query Orchestrator** | Docker build → ACR → Container App update | Azure Container Apps | Shell script |
| **AEM Processor** | Docker build → ACR → Container App update | Azure Container Apps | Shell script |
| **Content Parser** | esbuild → zip → az webapp deploy | Azure Functions | Shell script |
| **Chat UI** | swa deploy | Azure Static Web Apps | Shell script |

### 7.2 Container App Deployment (Query Orchestrator)

```bash
./scripts/deploy-query-orchestrator.sh [environment] [tag]
```

**Deployment flow:**
```
1. Determine image tag
   ├── Explicit tag: ./deploy.sh dev v1.0.0
   └── Auto tag: git SHA (e.g., "a1b2c3d")
       └── If dirty working tree: "a1b2c3d-dirty"

2. Dirty deploy protection
   ├── dev: allowed (warning)
   ├── staging: BLOCKED
   └── prod: BLOCKED

3. Build Docker image
   └── docker build --platform linux/amd64 -t $ACR/$IMAGE:$TAG

4. Push to ACR
   ├── Push SHA-tagged image
   └── Push "latest" tag

5. Update Container App
   └── az containerapp update --image $ACR/$IMAGE:$TAG

6. Verify
   ├── curl /health
   └── curl /status
```

**Why git SHA tags?** *"Every deployment is traceable to a specific commit. If something breaks, we know exactly which code is running. The 'dirty' suffix prevents accidental production deploys of uncommitted code."*

**Rollback:** *"Rolling back is just redeploying the previous git SHA: `./deploy.sh prod abc1234`. Container Apps maintains revision history, so Azure also supports revision-based rollback."*

---

### 7.3 Azure Functions Deployment (Content Parser)

```bash
./scripts/deploy-content-parser.sh
```

**Deployment flow:**
```
1. Install pnpm dependencies
2. Build workspace packages (shared-types, shared-config, azure-services, prisma-config)
3. Generate Prisma client
4. Bundle with esbuild (single file: dist/index.js)
5. Create function.json for blob trigger
6. Copy Prisma client native binary
7. Create deploy.zip
8. az webapp deploy --type zip --async true
```

**Why `--async true`?** *"Azure's deployment status polling (Kudu) sometimes returns empty JSON responses, causing CLI errors. Async deploy fires-and-forgets the zip upload, avoiding this issue. We verify deployment separately."*

---

### 7.4 Terraform Deployment

```bash
# Per-environment deployment
cd infra/environments/dev

# Initialize (first time or after module changes)
terraform init -backend-config=backend.tfvars

# Plan (always review before applying)
terraform plan -out=tfplan

# Apply
terraform apply tfplan

# Or use convenience scripts:
./infra/scripts/init.sh dev
./infra/scripts/plan.sh dev
./infra/scripts/apply.sh dev
```

**Deployment philosophy: Incremental validation**
1. Deploy one module at a time
2. Validate in Azure Portal
3. Test functionality
4. Proceed to next module
5. Total deployment time: ~45-60 minutes (APIM alone takes 30-45 min)

---

### 7.5 Environment Promotion

```
dev (public endpoints, basic SKUs, $225/mo)
  │
  ▼  Manual promotion (test in dev → plan in nonprod)
nonprod (private endpoints, VNet, standard SKUs)
  │
  ▼  Manual promotion (validation → plan in prod)
prod (private endpoints, premium SKUs, HA, ~$2000/mo)
```

**Why manual, not automated CI/CD?** *"For Phase 1 (MVP demo), the team is 2-4 people and deployment frequency is low (weekly at most). We prioritize understanding and validating each deployment over automation speed. CI/CD pipelines are planned for Phase 2 when we have a stable deployment pattern."*

---

## 8. Observability & Monitoring

### 8.1 Telemetry Stack

```
Application Insights (appi-con-nav-dev)
  ├── Distributed tracing (end-to-end request correlation)
  ├── Live Metrics (real-time dashboard)
  ├── Application Map (service dependency visualization)
  └── Smart Detection (anomaly detection)

Log Analytics Workspace (log-con-nav-dev)
  ├── 30-day retention
  ├── KQL queries
  └── Receives diagnostic logs from ALL services:
      ├── Azure OpenAI
      ├── AI Search
      ├── Content Safety
      ├── PostgreSQL
      ├── API Management
      ├── Container Apps
      ├── Azure Functions
      └── Key Vault
```

### 8.2 Structured Log Schema

Every log entry from Query Orchestrator includes:

| Field | Description |
|-------|-------------|
| `timestamp` | ISO8601 |
| `trace_id` | Correlation ID for distributed tracing |
| `session_id` | Client session (from `x-session-id` header) |
| `agent_id` | Which agent handled the request |
| `agent_version` | Service version |
| `operation` | Operation name (e.g., `chat.request`, `search.execute`) |
| `latency_ms` | Operation duration |
| `query_hash` | SHA256 of query (NOT raw query — privacy) |

**Why query hash, not raw query?** *"We never log raw user queries — they could contain PII. We log a SHA256 hash for correlation and debugging. If we need to see the actual query, it's in PostgreSQL (with access controls), not in centralized logs."*

### 8.3 Key Metrics & SLAs

| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| Query latency (P50) | < 1.5s | — |
| Query latency (P95) | < 3s | P95 > 3s |
| Streaming start time | < 500ms | — |
| Availability | > 99% | < 99% |
| Error rate | < 2% | > 5% |
| Token usage | Within quota | > 80% quota |

### 8.4 Health Check Design

```
/health (liveness probe)
  └── Returns 200 if process is running
      Used by: Container Apps liveness probe
      Interval: 30s, timeout: 5s, failures: 3

/health/ready (readiness probe)
  └── Checks connectivity to:
      ├── Azure OpenAI ✅/❌
      ├── Azure AI Search ✅/❌
      ├── Azure Content Safety ✅/❌
      ├── Azure AI Language ✅/❌
      ├── Database ✅/❌
      └── Application Insights ✅/❌
      Used by: Container Apps readiness probe
      Interval: 10s, timeout: 5s, failures: 3
```

**Why separate probes?** *"Liveness tells Kubernetes/Container Apps 'is the process alive?' — if it fails, the container is restarted. Readiness tells 'can it serve traffic?' — if it fails, traffic is routed to other replicas but the container is NOT restarted. This prevents cascading restarts when an upstream dependency is temporarily down."*

---

## 9. Networking & Connectivity

### 9.1 Current State (Dev — Phase 1)

```
All services have PUBLIC endpoints
No VNet, no private endpoints
APIM Developer SKU (no VNet integration)

Traffic flow:
  User → Lumen WAF → APIM (public) → Container App (public)
  Container App → Azure OpenAI (public)
  Container App → AI Search (public)
  Content Parser → Blob Storage (public, managed identity)
```

### 9.2 Target State (Nonprod/Prod — Phase 2)

```
DMZ Subscription (Lumen-provided)
  └── DMZ VNet
      └── APIM (Premium, VNet-integrated)

Commercial Subscription (existing)
  └── Commercial VNet
      ├── Container Apps Subnet (delegated: Microsoft.App/environments)
      │   ├── Query Orchestrator (internal ingress only)
      │   └── AEM Processor (internal ingress only)
      ├── Functions Subnet (delegated: Microsoft.Web/serverFarms)
      │   └── Content Parser
      ├── Private Endpoints Subnet
      │   ├── PE for Azure OpenAI
      │   ├── PE for AI Search
      │   ├── PE for Blob Storage
      │   ├── PE for PostgreSQL
      │   ├── PE for Key Vault
      │   ├── PE for ACR
      │   └── PE for Redis
      └── NAT Gateway (egress for AEM scraping)

VNet Peering: DMZ VNet ←→ Commercial VNet
```

**Interview answer on evolution:** *"In dev we deliberately use public endpoints to simplify initial development and debugging. For nonprod/prod, we implement full VNet isolation: Container Apps deploy into a delegated subnet, all PaaS services are accessible only via private endpoints, and external traffic flows through APIM in the DMZ subscription via VNet peering. The NAT Gateway provides a fixed egress IP for scraping AEM."*

---

## 10. Cost Engineering

### 10.1 Cost Breakdown

| Service | Dev SKU | Dev Cost | Prod SKU | Prod Cost |
|---------|---------|----------|----------|-----------|
| Azure OpenAI | Standard | $50-100 | Standard | $500 |
| AI Search | Standard | $250 | Standard (2 replicas) | $500 |
| APIM | Developer | $50 | Premium | $2,800 |
| PostgreSQL | B_Standard_B1ms | $25 | GP_Standard_D2s_v3 | $150 |
| Container Apps | Consumption | $20 | Consumption | $50 |
| Functions | Y1 (Consumption) | $10 | EP1 (Premium) | $150 |
| Redis | Balanced_B1 | $50 | Balanced_B3 | $200 |
| Storage | Standard LRS | $5 | Standard GRS | $15 |
| Static Web Apps | Free | $0 | Standard | $10 |
| App Insights | Pay-as-you-go | $10 | Pay-as-you-go | $50 |
| **Total** | | **~$470/mo** | | **~$4,425/mo** |

### 10.2 Cost Optimization Strategies

1. **Consumption tiers for dev** — Functions Y1, Container Apps consumption
2. **Redis caching** — 60-80% reduction in Azure OpenAI API calls
3. **Sampling in App Insights** — 100% in dev, 20% in prod for high traffic
4. **Reserved capacity** — 30% discount for 1-year commitment on prod
5. **Token monitoring** — Set budget alerts at 80% of quota
6. **Auto-scaling thresholds** — Scale down to 1 replica in off-hours
7. **Blob lifecycle policies** — Archive old raw HTML after 90 days

---

## 11. Disaster Recovery & Reliability

### 11.1 Current State (Dev)

| Capability | Status |
|-----------|--------|
| Backups | PostgreSQL: 7-day retention |
| Geo-redundancy | ❌ None (LRS storage) |
| Multi-region | ❌ Single region (East US 2) |
| HA | ❌ No HA for PostgreSQL |
| RTO | ~2 hours (Terraform redeploy) |
| RPO | ~24 hours (daily backup) |

### 11.2 Target State (Prod)

| Capability | Status |
|-----------|--------|
| Backups | PostgreSQL: 35-day retention |
| Geo-redundancy | ✅ GRS storage, geo-replicated ACR |
| Multi-region | ✅ Active-passive (East US 2 / Central US) |
| HA | ✅ PostgreSQL Zone-Redundant HA |
| RTO | < 30 minutes |
| RPO | < 1 hour |

### 11.3 Blast Radius Containment

- Separate Terraform state per environment
- `prevent_deletion_if_contains_resources = true` on resource groups
- Key Vault `purge_soft_delete_on_destroy = false`
- Blob versioning + 30-day soft delete
- Container App revision history for instant rollback

---

## 12. Interview Q&A

### Architecture & Design

**Q1: Walk me through the system architecture.**
> "This is a RAG (Retrieval-Augmented Generation) platform on Azure. Two pipelines: ingestion and query. Ingestion: AEM CMS publishes events → Storage Queue → Container App scrapes with Playwright → HTML to Blob Storage → Azure Function converts to Markdown → Azure AI Search indexes with embeddings. Query: User → WAF → APIM (rate limiting) → Query Orchestrator Container App → guardrails check → hybrid search (BM25 + vector) → Azure OpenAI generates response with citations → SSE stream back to user."

**Q2: Why did you choose RAG over fine-tuning?**
> "Three reasons: content freshness (we update within minutes of a CMS publish), cost (no retraining), and grounded citations (every response links to source URLs). Fine-tuning can still hallucinate; RAG responses are always grounded in retrieved documents."

**Q3: How do you handle search relevance?**
> "Three layers: BM25 keyword matching for exact terms, cosine similarity vector search for semantic meaning, and optional semantic reranking as an L2 pass using Microsoft's models. Hybrid search uses Reciprocal Rank Fusion to combine scores. We retrieve 50 candidates, rerank, and pass top 10 to the LLM."

**Q4: Why a monorepo?**
> "Shared TypeScript types between 4 packages, shared Prisma schema used by 3 packages, atomic commits for cross-package changes, and pnpm's strict dependency resolution prevents phantom dependencies."

**Q5: What's your multi-agent strategy?**
> "Built on Microsoft Agent Framework from day one. The RAG search is our first agent. Each agent implements a standard interface (invoke, stream, capability). An AgentRouter selects the appropriate agent based on the query. Currently single-agent (always RAG), but the architecture supports adding Calendly scheduling, form population, and product comparison agents without refactoring."

---

### Infrastructure & Terraform

**Q6: How is your Terraform organized?**
> "15 reusable modules organized by Azure service domain, composed in environment-specific main.tf files. Each environment (dev/nonprod/prod) has its own state file, backend config, and variable values. Role assignments are in a dedicated module to avoid circular dependencies — you can't assign a role before the identity exists."

**Q7: How do you manage Terraform state?**
> "Azure Storage backend with blob lease locking. State is encrypted with infrastructure encryption, versioned, and soft-delete enabled. We bootstrap the state backend separately from the main infrastructure to avoid the chicken-and-egg problem."

**Q8: How do you handle secrets in Terraform?**
> "Three secrets in Key Vault: database password, database URL, and gateway secret. Azure Functions consume via Key Vault references (`@Microsoft.KeyVault(SecretUri=...)`). Container Apps get secrets injected by Terraform at deployment time. Everything else uses Managed Identity — no API keys."

**Q9: What's your environment promotion strategy?**
> "Dev → Nonprod → Prod. Dev uses public endpoints and basic SKUs for simplicity. Nonprod mirrors prod's network topology (VNet + private endpoints) at lower scale. Prod uses premium SKUs, HA PostgreSQL, and multi-region. Promotion is manual with plan-review-apply — we prioritize understanding over automation at this scale."

**Q10: How do you handle Terraform module dependencies?**
> "Terraform's dependency graph handles most of it through module output references. The key decision is separating role-assignments into its own module — it depends on all other modules' principal_ids. We also use `count` with conditional checks (`principal_id != null`) to handle optional resources."

---

### Security

**Q11: How do you secure service-to-service communication?**
> "Zero API keys. Every Azure service uses SystemAssigned Managed Identity. We assign RBAC roles via Terraform — Cognitive Services OpenAI User for OpenAI, Search Index Data Reader for AI Search, etc. The only traditional secrets are the database password and APIM gateway secret, both stored in Key Vault."

**Q12: How do you prevent prompt injection?**
> "Multi-layer guardrails pipeline. First: input validation (length, sanitization). Second: PII detection via Azure AI Language (redact SSN, phone numbers). Third: Azure AI Content Safety's Prompt Shield — it specifically detects prompt injection patterns like 'ignore your instructions' or hidden instructions in retrieved content."

**Q13: How do you prevent direct access to the backend?**
> "APIM injects an X-Gateway-Secret header (value from Key Vault). The Query Orchestrator validates this header when ENFORCE_GATEWAY_VALIDATION is true. Direct requests without the header get 403. This forces all traffic through APIM's rate limiting."

**Q14: What's your Key Vault strategy?**
> "RBAC authorization model (not access policies). Purge protection enabled. Every consuming service gets Key Vault Secrets User role via Managed Identity. Audit logging to Log Analytics. Only 3 secrets stored — everything else is Managed Identity."

**Q15: How do you handle data protection?**
> "Encryption at rest on all services (Azure-managed keys). TLS 1.2+ enforced everywhere. No raw queries in logs — we use SHA256 hashes. PII detection before LLM processing. Blob versioning and soft delete for data recovery. Data classification tag on every resource."

---

### Deployment & Operations

**Q16: How do you deploy container apps?**
> "Shell script: build Docker image tagged with git SHA, push to ACR (both SHA tag and 'latest'), update Container App via `az containerapp update`. Dirty deploy protection blocks uncommitted code from reaching staging/prod. Rollback is redeploying a previous SHA."

**Q17: How do you deploy Azure Functions?**
> "esbuild bundles TypeScript into a single file, we copy Prisma client binaries separately, zip the result, and use `az webapp deploy --type zip --async true`. The async flag avoids Kudu polling failures."

**Q18: What's your container image strategy?**
> "Two tags per build: git SHA (e.g., 'a1b2c3d') for traceability and 'latest' for convenience. Container Apps always reference the SHA tag, not latest, so we know exactly what's running. Non-root user in Dockerfile for security."

**Q19: How do you handle database migrations?**
> "Prisma ORM with migration files. Local dev runs `prisma migrate dev`. Prod runs `prisma migrate deploy`. Schema is defined once in `packages/prisma-config/prisma/schema.prisma` and shared across all TypeScript packages."

**Q20: What's your local development setup?**
> "docker-compose with PostgreSQL (pgvector), Redis, and Azurite (Azure Storage emulator). Content ingestion pipeline runs fully local — `pnpm dev:ingestion` starts both AEM Processor and Content Parser against Azurite. Query Orchestrator runs locally with `uvicorn` and uses `az login` credentials to access Azure AI services."

---

### Monitoring & Troubleshooting

**Q21: How do you trace a request end-to-end?**
> "Application Insights distributed tracing. Every request gets a trace_id propagated through APIM → Container App → Azure OpenAI → AI Search. We can see the full waterfall in Application Insights' Transaction Search — API latency, search latency, LLM latency, total E2E time."

**Q22: What are your key SLIs/SLOs?**
> "Availability > 99%. Query latency P95 < 3 seconds. Streaming start time < 500ms. Error rate < 2%. These are measured via Application Insights custom metrics."

**Q23: How do you handle upstream service failures?**
> "Readiness probe checks all dependencies. If AI Search or OpenAI is down, the readiness probe fails and Container Apps stops routing traffic to that replica. Guardrails services (Content Safety, Language) degrade gracefully — if they're unreachable, we log a warning and continue processing (fail-open for guardrails, fail-closed would block all queries)."

**Q24: What alerts do you have?**
> "Critical: availability < 99%, error rate > 5%, latency P95 > 5s, API quota exceeded. Warning: unusual traffic patterns, token usage > 80%, storage > 80%, database connection issues."

**Q25: How do you debug production issues?**
> "KQL queries in Log Analytics for centralized log search. Application Insights Live Metrics for real-time monitoring. Container App log streaming via `az containerapp logs show --follow`. Structured JSON logging with correlation IDs for request tracing."

---

### Cost & Scaling

**Q26: How do you optimize costs?**
> "Dev uses consumption/basic tiers everywhere. Redis caching reduces OpenAI API calls by 60-80%. App Insights sampling for high-traffic scenarios. Container Apps scale to zero when possible (not for always-on services). Budget alerts at 80% threshold. Reserved capacity for prod (30% savings)."

**Q27: How does auto-scaling work?**
> "Container Apps: KEDA-based scaling from 1 to 3 replicas (dev) or 1 to 10 (prod) based on HTTP request count. Azure Functions: consumption plan scales automatically based on blob trigger queue depth. AI Search: manual scaling via replica count."

**Q28: What's your capacity planning approach?**
> "Monitor token usage against Azure OpenAI quota. AI Search indexing throughput determines content pipeline capacity. Container App replica count for query throughput. We estimate ~$470/month for dev and ~$4,425/month for prod at full scale."

---

### Scenarios & Problem-Solving

**Q29: A user reports slow responses. How do you diagnose?**
> "1. Check Application Insights for P95 latency trend. 2. Look at the distributed trace — is it search latency, LLM latency, or guardrails? 3. Check if Container App is at max replicas (scaling bottleneck). 4. Check Azure OpenAI token utilization (throttling). 5. Check Redis cache hit ratio — cache misses mean every query hits OpenAI."

**Q30: Your Azure OpenAI quota is exhausted. What do you do?**
> "Immediate: enable Redis caching if not already active. Short-term: increase TPM quota in Azure Portal. Medium-term: implement semantic caching (similar queries return cached responses). Long-term: model flexibility — switch to a cheaper model (GPT-4.1-nano for simple queries) or Azure AI Foundry for alternative models."

**Q31: You need to add a new AI service. Walk through the process.**
> "1. Create Terraform resource in ai-services module. 2. Add output for endpoint and resource ID. 3. Create role assignment in role-assignments module (managed identity access). 4. Add environment variable to container-apps module. 5. Add endpoint to Query Orchestrator config.py (Pydantic Settings). 6. Implement the service client in Python. 7. `terraform plan` → `terraform apply` → deploy container."

**Q32: Production database is running out of storage. What's your plan?**
> "Immediate: increase storage_mb in Terraform (online resize, no downtime). Short-term: analyze storage usage — are we logging too many queries? Enable query log rotation. Medium-term: implement data retention policies — archive old query logs to blob storage. Long-term: evaluate if we need a time-series database for analytics data."

**Q33: How would you implement blue-green deployments?**
> "Container Apps supports revision-based traffic splitting. Deploy new revision (green), send 10% traffic, monitor errors and latency, gradually increase to 100%, then deactivate old revision (blue). The revision_mode is currently 'Single' — we'd change to 'Multiple' and use traffic_weight blocks."

**Q34: How would you add CI/CD?**
> "GitHub Actions workflow: on push to main → run tests → build Docker images → push to ACR → update Container Apps (dev auto-deploy). PR to release branch → deploy to nonprod. Tag release → manual approval gate → deploy to prod. Terraform changes would go through a plan-comment-approve flow in PR."

**Q35: The search index returns irrelevant results. How do you improve relevance?**
> "1. Enable semantic reranking (already supported, just toggle `azure_search_semantic_enabled=true`). 2. Tune chunk size and overlap (currently 2000/500). 3. Improve content parsing (better HTML cleaning). 4. Add field boosting (boost title matches over content). 5. Phase 3: train a custom ML reranking model using click-through data."

---

### Advanced / Senior-Level

**Q36: How do you ensure embedding model consistency?**
> "Critical rule: NEVER change embedding models after indexing. Vectors from different models are incompatible. We use text-embedding-ada-002 (1536 dimensions) for all environments and document this as an architectural constraint. If we ever need to change the embedding model, it requires full re-indexing of all content."

**Q37: How does the event-driven ingestion pipeline handle failures?**
> "Storage Queue provides at-least-once delivery with visibility timeout. If the AEM Processor crashes mid-scrape, the message becomes visible again after the timeout and gets reprocessed. Failed messages go to a dead letter queue after max retries. The Content Parser is idempotent — re-processing the same HTML produces the same markdown."

**Q38: How do you handle the two-language stack (TypeScript + Python)?**
> "Clear separation: TypeScript for content pipeline (same language as CMS integration), Python for AI orchestration (best AI/ML ecosystem). Shared contract via the search index schema — TypeScript writes to it, Python reads from it. No runtime coupling between the two stacks. Deployment scripts are per-language."

**Q39: What's your approach to testing AI systems?**
> "Unit tests for guardrails (validation rules, PII patterns). Integration tests with Azure services (requires RBAC). Security tests (prompt injection test cases). Red-team evaluation via promptfoo (YAML-based test suites). Benchmarks for latency targets. We don't unit test LLM outputs — we test the pipeline around the LLM."

**Q40: How would you migrate from Container Apps to AKS if needed?**
> "The Dockerfiles are portable — no Container Apps lock-in. We'd create AKS Terraform modules, write Kubernetes manifests (Deployment, Service, Ingress, HPA), set up AAD Pod Identity for managed identity, configure KEDA for autoscaling, and update APIM backend URLs. The application code doesn't change."

---

### DevOps Philosophy

**Q41: What's your deployment philosophy?**
> "Incremental validation. Deploy one module at a time, verify in portal, test functionality, then proceed. We prefer understanding over speed at this scale. Every deployment is reversible — Container App revisions for apps, Terraform state for infrastructure."

**Q42: How do you handle configuration management?**
> "Terraform for infrastructure config. Environment variables for application config. Key Vault for secrets. Pydantic Settings in Python validates all config at startup with type safety. No config files in containers — everything via env vars and secrets."

**Q43: What's your approach to documentation?**
> "Architecture as code — the Terraform modules are the source of truth for infrastructure. Each doc covers a specific audience: ARCHITECTURE.md for developers, AZURE_INFRASTRUCTURE_OVERVIEW.md for security reviewers, DEPLOYMENT.md for operators, LOCAL_DEVELOPMENT.md for new team members."

**Q44: How do you handle tech debt?**
> "Phased approach. Phase 1: MVP with public endpoints, basic SKUs, manual deployment. Phase 2: private endpoints, VNet isolation, CI/CD, Redis caching. Phase 3: custom ML reranking, multi-region, advanced analytics. Each phase is a complete working system, not half-finished features."

**Q45: What would you do differently if starting over?**
> "1. Start with VNet from day one — retrofitting private endpoints is harder than starting with them. 2. CI/CD from the start — even simple GitHub Actions. 3. Use Terraform workspaces instead of separate directories per environment. 4. Consider Azure Developer CLI (azd) for opinionated deployment."

---

### Networking-Specific

**Q46: Explain the DMZ / Commercial subscription architecture.**
> "Two Azure subscriptions connected via VNet peering. DMZ subscription (Lumen-provided) hosts APIM Premium with VNet integration behind Lumen's WAF. Commercial subscription hosts all workloads in a private VNet — Container Apps in a delegated subnet, Functions in another, and private endpoints for all PaaS services in a third. The only public-facing endpoint is the APIM gateway in the DMZ."

**Q47: Why NAT Gateway?**
> "The AEM Content Processor needs to scrape external URLs (lumen.com). With all services in a private VNet, outbound traffic needs a path. NAT Gateway provides a fixed egress IP, which Lumen's network team can whitelist in their firewall rules."

**Q48: How do private endpoints work in your setup?**
> "Each PaaS service (OpenAI, Search, Storage, PostgreSQL, Key Vault, ACR, Redis) gets a private endpoint in a dedicated subnet. Azure Private DNS zones resolve the service FQDN to the private IP instead of the public IP. This means traffic between Container Apps and Azure services never leaves the Microsoft backbone."

---

### AI/ML Specific

**Q49: How do you handle model versioning and upgrades?**
> "Azure OpenAI deployments are pinned to specific model versions in Terraform (e.g., gpt-5-mini version 2025-08-07). We upgrade by changing the Terraform variable, running plan/apply, and testing. The config-driven approach means we can switch models (GPT-4.1, GPT-5, Claude) by changing environment variables — no code changes."

**Q50: What's your approach to responsible AI?**
> "Multi-layer: input guardrails (PII detection, prompt injection), model-level (Azure OpenAI's built-in content filters), output guardrails (planned — content moderation on generated responses). We classify all data as public with no PII. Azure AI Content Safety provides the Prompt Shield capability specifically designed for RAG systems."

---

## 13. Quick Reference Cards

### 13.1 Azure Resource Inventory (Dev)

| Resource | Type | SKU |
|----------|------|-----|
| `rg-con-nav-dev` | Resource Group | — |
| `ai-con-nav-dev` | Azure OpenAI | S0 |
| `cs-con-nav-dev` | AI Content Safety | S0 |
| `lang-con-nav-dev` | AI Language | S |
| `search-con-nav-dev` | AI Search | Standard |
| `psql-con-nav-dev` | PostgreSQL v16 | B_Standard_B1ms |
| `connavdevstdec2025` | Storage Account | Standard LRS |
| `redis-con-nav-dev` | Managed Redis | Balanced_B1 |
| `kv-con-nav-dev` | Key Vault | Standard |
| `apim-con-nav-dev` | API Management | Developer_1 |
| `lumenconvnavdev` | Container Registry | Basic |
| `lumen-query-orchestrator-dev` | Container App | 0.5 CPU / 1Gi |
| `lumen-aem-processor-dev` | Container App | 1.0 CPU / 2Gi |
| `func-parser-con-nav-dev` | Azure Function | Y1 Consumption |
| `func-indexer-con-nav-dev` | Azure Function | Y1 Consumption |
| `log-con-nav-dev` | Log Analytics | PerGB2018 |
| `appi-con-nav-dev` | App Insights | — |

### 13.2 Deployed Model Inventory

| Model | Deployment Name | TPM | Purpose |
|-------|----------------|-----|---------|
| text-embedding-ada-002 | text-embedding-ada-002 | 900 | Embeddings (1536 dim) |
| gpt-5-mini | gpt-5-mini | 120 | Chat generation |
| gpt-4.1-nano | gpt-4-1-nano | 60 | Intent classification |

### 13.3 Key Endpoints (Dev)

| Service | URL |
|---------|-----|
| APIM Gateway | `https://apim-con-nav-dev.azure-api.net` |
| Query Orchestrator | `https://lumen-query-orchestrator-dev.proudsky-c25471ee.eastus2.azurecontainerapps.io` |
| Azure OpenAI | `https://ai-con-nav-dev.openai.azure.com/` |
| AI Search | `https://search-con-nav-dev.search.windows.net` |
| PostgreSQL | `psql-con-nav-dev.postgres.database.azure.com:5432` |

### 13.4 Essential Commands

```bash
# Infrastructure
terraform init -backend-config=backend.tfvars
terraform plan -out=tfplan
terraform apply tfplan
terraform output

# Deployments
./scripts/deploy-query-orchestrator.sh dev
./scripts/deploy-content-parser.sh
./scripts/deploy-aem-processor.sh dev
./scripts/deploy-chat-ui.sh

# Health checks
curl https://apim-con-nav-dev.azure-api.net/chat/health
curl https://apim-con-nav-dev.azure-api.net/chat/status

# Logs
az containerapp logs show --name lumen-query-orchestrator-dev \
  --resource-group rg-con-nav-dev --follow

# Local development
docker-compose up -d              # Start PostgreSQL + Azurite + Redis
pnpm dev:ingestion                # Start content pipeline
pnpm send-test-message <url>      # Test content ingestion
uvicorn src.main:app --reload     # Start Query Orchestrator locally
```

### 13.5 Terraform Module Quick Reference

| Module | Creates | Key Variables |
|--------|---------|---------------|
| `shared` | Resource Group | `resource_group_name`, `location` |
| `monitoring` | Log Analytics, App Insights | `retention_in_days`, `sampling_percentage` |
| `storage` | Storage Account, Blob Containers, Queues | `replication_type`, `blob_retention_days` |
| `ai-services` | OpenAI, Content Safety, Language | `gpt_deployment_name`, `embedding_capacity` |
| `search` | AI Search, Index, Indexer, Skillset | `sku`, `semantic_search_sku`, `chunk_size` |
| `database` | PostgreSQL Flexible Server | `sku_name`, `storage_mb`, `postgresql_version` |
| `key-vault` | Key Vault + 3 secrets | `db_admin_password`, `gateway_secret` |
| `compute` | Functions (Content Parser, Index Orchestrator) | `sku_name`, `app_settings` |
| `container-apps` | ACR, Container App Env, 2 Container Apps | `cpu`, `memory`, `min/max_replicas` |
| `api-gateway` | APIM + APIs + Policies | `sku_name`, `gateway_secret`, `cors_origins` |
| `caching` | Azure Managed Redis | `sku_name`, `enable_redis` |
| `role-assignments` | ~15 RBAC assignments | `*_principal_id`, `*_account_id` |
| `static-web-app` | Static Web App (Chat UI) | `sku_tier` |

---

## Final Study Tips

1. **Start with the elevator pitch** — demonstrate you understand the business value
2. **Draw the architecture** — keep two diagrams ready: ingestion pipeline + query pipeline
3. **Lead with "why"** — interviewers care more about WHY you chose something than WHAT you chose
4. **Know the trade-offs** — for every decision, know what you gave up
5. **Cost numbers matter** — knowing $470/dev vs $4,425/prod shows senior-level awareness
6. **Security is a first-class citizen** — Managed Identity everywhere, guardrails pipeline, Key Vault
7. **Phased approach** — demonstrate you can deliver incrementally, not just plan for perfection
8. **Be honest about gaps** — "We don't have CI/CD yet because [reason], and here's our plan"

---

*Document generated from codebase analysis on May 22, 2026. Based on commit `c1f6268`.*
