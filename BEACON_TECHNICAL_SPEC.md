# 🔦 Beacon — Complete Technical Specification & System Design Document

**Version:** 1.0.0  
**Date:** June 13, 2026  
**Authors:** Team FineTunners (Aryan Singh, Sandeep Prajapati, Kurian Jose, Preet Biswas)  
**Repository:** https://github.com/DevAryanSin/BeaconBRD  
**Live Demo:** https://beacon.sandeepp.in/

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Overview](#2-product-overview)
3. [System Architecture](#3-system-architecture)
4. [Technology Stack](#4-technology-stack)
5. [Frontend Architecture](#5-frontend-architecture)
6. [Backend Architecture](#6-backend-architecture)
7. [AI/ML Pipeline](#7-aiml-pipeline)
8. [Database Design](#8-database-design)
9. [API Reference](#9-api-reference)
10. [Security Architecture](#10-security-architecture)
11. [Deployment Architecture](#11-deployment-architecture)
12. [Data Flow Diagrams](#12-data-flow-diagrams)
13. [Feature Deep-Dive](#13-feature-deep-dive)
14. [Project Rating & Honest Assessment](#14-project-rating--honest-assessment)

---

## 1. Executive Summary

Beacon is a **full-stack AI-powered Business Requirements Document (BRD) generation platform**. It solves a real business problem: product teams scatter requirements across Slack threads, emails, meeting notes, and file uploads, making BRD creation a days-long manual synthesis exercise.

**Beacon automates this entirely.** Users ingest raw communications from multiple sources, and the platform's AI pipeline filters noise, classifies signals, and generates a structured, professional BRD through 7 specialized AI agents running in parallel — all reviewable and exportable from a modern web UI.

**What makes it technically interesting:**
- Two-phase AI noise filter (heuristics + LLM batch classification) that reduces API costs by ~40-60%
- 3-phase multi-agent BRD generation pipeline with ThreadPoolExecutor parallelism
- Human-in-the-loop versioning with section locking
- Dual orchestration engines (legacy ThreadPoolExecutor + Google ADK)
- Real-time SSE streaming of agent progress
- Multi-format export (Markdown, HTML, DOCX, PDF) with full markdown parsing
- Graceful degradation: SQLite fallback, heuristic fallback when LLM is unavailable

---

## 2. Product Overview

### Problem Statement

```
Slack threads  ──┐
Email chains   ──┤
Meeting notes  ──┼──→  🔥 Requirements Lost, Contradicted, or Forgotten
File uploads   ──┤
Verbal calls   ──┘
```

### The 4-Step Workflow

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────────┐
│  1. INGEST   │───▶│  2. CLASSIFY  │───▶│  3. GENERATE │───▶│  4. EXPORT  │
│              │    │              │    │              │    │             │
│ Upload files │    │ AI separates │    │ 7 AI agents  │    │ .md .html   │
│ Connect Slack│    │ signals from │    │ write BRD    │    │   .docx     │
│ Run demo     │    │ noise        │    │ sections     │    │             │
└─────────────┘    └──────────────┘    └──────────────┘    └─────────────┘
```

### Target Users

| User | Benefit |
|------|---------|
| **Product Managers** | First draft in under 10 minutes; share boards with stakeholders |
| **Engineering Teams** | Auto-extracted functional requirements, deduplicated |
| **Business Analysts** | HITL editing, validation flags, polished DOCX export |
| **Team Leads** | Role-based board sharing, session history, version tracking |

---

## 3. System Architecture

### High-Level Component Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER BROWSER                                  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              Next.js 14 App (React 18 + TypeScript 5)         │  │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │  │
│  │  │  Auth   │ │Ingestion │ │BRD Editor│ │  Export/Share    │ │  │
│  │  │ Context │ │  Panel   │ │  (HITL)  │ │  (md/html/docx)  │ │  │
│  │  └────┬────┘ └────┬─────┘ └────┬─────┘ └────────┬─────────┘ │  │
│  │       │           │            │                 │            │  │
│  │  ┌────┴───────────┴────────────┴─────────────────┴─────────┐  │  │
│  │  │          Zustand Stores (useBRDStore, useAuthStore)     │  │  │
│  │  └────┬────────────────────────────────────────────────────┘  │  │
│  └───────┼───────────────────────────────────────────────────────┘  │
└──────────┼──────────────────────────────────────────────────────────┘
           │ HTTPS / SSE / REST
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND (Python 3.11+)                    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    api/main.py (CORS + Middleware)             │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────┐ ┌──────────┐ │  │
│  │  │ Sessions │ │ Ingestion│ │  BRD   │ │ HITL │ │  Slack   │ │  │
│  │  │ Router   │ │ Router   │ │ Router │ │Router│ │  Router  │ │  │
│  │  └────┬─────┘ └────┬─────┘ └───┬────┘ └──┬───┘ └────┬─────┘ │  │
│  └───────┼─────────────┼──────────┼─────────┼──────────┼────────┘  │
│          │             │          │         │          │            │
│  ┌───────┴─────────────┴──────────┴─────────┴──────────┴────────┐  │
│  │                     CORE MODULES                               │  │
│  │  ┌──────────────────┐  ┌──────────────────────────────────┐  │  │
│  │  │  Noise Filter    │  │        BRD Module                │  │  │
│  │  │  Module          │  │  ┌────────────┐ ┌─────────────┐  │  │  │
│  │  │  ┌────────────┐  │  │  │ brd_pipeline│ │  validator  │  │  │  │
│  │  │  │classifier  │  │  │  │ (7 agents) │ │  (AI+rules) │  │  │  │
│  │  │  │(2-phase)   │  │  │  └────────────┘ └─────────────┘  │  │  │
│  │  │  ├────────────┤  │  │  ┌────────────┐ ┌─────────────┐  │  │  │
│  │  │  │prompts     │  │  │  │  exporter   │ │versioned    │  │  │  │
│  │  │  ├────────────┤  │  │  │(md/html/    │ │ledger (HITL)│  │  │  │
│  │  │  │schema      │  │  │  │ docx/pdf)   │ └─────────────┘  │  │  │
│  │  │  └────────────┘  │  │  └────────────┘                    │  │  │
│  │  └──────────────────┘  │  ┌──────────────────────────────┐  │  │  │
│  │                        │  │  ADK Orchestrator (optional)  │  │  │  │
│  │                        │  │  (Google ADK + refinement)    │  │  │  │
│  │                        │  └──────────────────────────────┘  │  │  │
│  │                        └──────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────┬──────────────────────┬──────────────────┬────────────────┘
           │                      │                  │
           ▼                      ▼                  ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│   PostgreSQL     │  │  Firebase        │  │    Groq Cloud        │
│   (Primary DB)   │  │  ┌────────────┐  │  │  ┌────────────────┐  │
│   ┌────────────┐ │  │  │   Auth     │  │  │  │ llama-3.3-70b  │  │
│   │classified_ │ │  │  │ (Email/    │  │  │  │ (BRD agents)   │  │
│   │chunks      │ │  │  │  Session)  │  │  │  ├────────────────┤  │
│   ├────────────┤ │  │  ├────────────┤  │  │  │ llama-4-scout  │  │
│   │brd_        │ │  │  │ Firestore  │  │  │  │ (classification│  │
│   │snapshots   │ │  │  │(Boards/    │  │  │  └────────────────┘  │
│   ├────────────┤ │  │  │ Members/   │  │  └──────────────────────┘
│   │brd_        │ │  │  │ Invites)   │  │
│   │sections    │ │  │  └────────────┘  │  ┌──────────────────────┐
│   ├────────────┤ │  └──────────────────┘  │  Google Cloud Vision  │
│   │brd_        │ │                        │  (OCR for PDFs/images)│
│   │validation_ │ │                        └──────────────────────┘
│   │flags       │ │
│   └────────────┘ │
│   SQLite fallback│
└──────────────────┘
```

### Runtime Responsibility Split

| Layer | Owns |
|-------|------|
| **Next.js Frontend** | UI rendering, authenticated routing, state management, collaboration UX |
| **Next.js API Routes** | Firebase session cookie management, server-only Firebase Admin calls |
| **FastAPI Backend** | All data processing, classification, generation, validation, export |
| **Firebase Auth** | User identity, JWT tokens, session cookies |
| **Firebase Firestore** | Board objects, member roles, invite tokens |
| **PostgreSQL / SQLite** | All AKS data — chunks, snapshots, sections, validation flags |
| **Groq LLM** | Email/text classification and all 7 BRD section agents |
| **Google Cloud Vision** | OCR for uploaded PDFs and images |

---

## 4. Technology Stack

### Frontend

| Technology | Version | Role |
|------------|---------|------|
| Next.js | 14.1.4 (App Router) | Full-stack React framework with SSR/SSG |
| TypeScript | 5.x | Type safety across all components |
| React | 18.x | UI component library |
| Tailwind CSS | 3.4 | Utility-first styling |
| Framer Motion | 11.x | Animations and transitions |
| Zustand | 5.x | Lightweight client-side state management |
| Firebase (Client) | 12.9 | Auth SDK and Firestore client |
| Firebase Admin | 13.6 | Server-side auth verification |
| Lucide React | 0.300 | Icon library |
| Radix UI | 2.x | Accessible headless UI primitives |
| date-fns | 4.1 | Date formatting |

### Backend

| Technology | Version | Role |
|------------|---------|------|
| FastAPI | ≥ 0.100 | High-performance REST API framework |
| Uvicorn | ≥ 0.22 | ASGI server |
| Python | 3.11+ | Runtime |
| Groq SDK | ≥ 0.4 | LLM inference (llama-3.3-70b-versatile, llama-4-scout) |
| Google ADK | Latest | Alternative agent orchestration engine |
| Pydantic | ≥ 2.0 | Request/response validation |
| psycopg2-binary | ≥ 2.9 | PostgreSQL driver |
| SQLite3 | Built-in | Local database fallback |
| python-docx | ≥ 0.8.11 | DOCX export with template support |
| WeasyPrint | ≥ 60 | HTML-to-PDF export |
| slack-sdk | ≥ 3.21 | Slack OAuth and API integration |
| PyMuPDF (fitz) | ≥ 1.22 | PDF text extraction |
| Google Cloud Vision | ≥ 3.4 | OCR for images and scanned PDFs |
| python-dotenv | ≥ 1.0 | Environment variable loading |
| markdown | ≥ 3.6 | Markdown-to-HTML conversion |

### Infrastructure

| Service | Purpose |
|---------|---------|
| Vercel | Frontend hosting (Next.js) |
| Render | Backend hosting (Docker container) |
| Firebase Auth | User authentication |
| Firebase Firestore | Board/member/invite data |
| PostgreSQL (Render/Supabase/Neon) | Primary database |
| Groq Cloud | LLM inference API |
| Google Cloud Vision | OCR processing |

---

## 5. Frontend Architecture

### Route Structure

```
/                          → Landing page (public)
/login                     → Email/password login (public)
/register                  → Account registration (public)
/forgot-password           → Password reset (public)
/dashboard                 → Session list + board overview (protected)
/ingestion                 → Data ingestion — upload, demo, Slack (protected)
/signals                   → Signal review — active and suppressed (protected)
/brd                       → BRD editor — sections, flags, editing (protected)
/brd/new                   → New BRD creation flow (protected)
/editor                    → Full BRD editor view (protected)
/export                    → Export as .md, .html, .docx, .pdf (protected)
/profile                   → Integrations (Slack, Gmail) and settings (protected)
/settings                  → Application settings (protected)
/agents                    → Agent orchestrator view (protected)
/analytics/conflicts       → Conflict detection dashboard (protected)
/analytics/sentiment       → Sentiment analysis (protected)
/analytics/traceability    → Signal traceability matrix (protected)
/signals                   → Signal management (protected)
/templates                 → BRD templates (protected)
/project/new               → Create new project (protected)
/project/[id]              → Project detail view (protected)
/invite/[token]            → Join a shared board via invite link (public)
/api/auth/session          → Firebase session cookie management (API route)
```

### State Management Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Zustand Stores                            │
│                                                             │
│  ┌─────────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  useAuthStore    │  │ useBRDStore  │  │useSessionStore│  │
│  │  - user          │  │ - sections   │  │ - sessions    │  │
│  │  - firebaseUser  │  │ - flags      │  │ - activeId    │  │
│  │  - loading       │  │ - snapshotId │  │ - history     │  │
│  └────────┬─────────┘  │ - generating │  └───────────────┘  │
│           │            └──────┬───────┘                      │
│  ┌────────┴──────────────────┴───────────────────────────┐  │
│  │              apiClient.ts (Typed Fetch Wrappers)       │  │
│  │  - createSession()    - generateBRD()   - getBRD()    │  │
│  │  - ingestChunks()     - editBRDSection() - exportBRD() │  │
│  │  - streamBRDGeneration() (EventSource/SSE)             │  │
│  │  - getSlackOAuthUrl() - ingestSlackChannels()          │  │
│  │  - getGmailOAuthUrl() - ingestGmailEmails()            │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Key Frontend Components

| Component | File | Purpose |
|-----------|------|---------|
| `AuthContext` | `contexts/AuthContext.tsx` | Global Firebase auth state provider |
| `useBRDStore` | `store/useBRDStore.ts` | BRD sections, flags, generation state |
| `apiClient` | `lib/apiClient.ts` | Typed fetch wrappers for all FastAPI endpoints |
| `AgentOrchestrator` | `components/workspace/AgentOrchestrator.tsx` | BRD generation UI + SSE stream consumer |
| `IngestionPanel` | `components/workspace/IngestionPanel.tsx` | File upload, demo ingest, log streaming |
| `BRDEditor` | `components/workspace/BRDEditor.tsx` | Section cards, human editing, lock control |
| `DashboardShell` | `components/layout/DashboardShell.tsx` | App layout wrapper with sidebar |
| `ShareBoardModal` | `components/ShareBoardModal.tsx` | Board sharing via invite links |
| `BackendWakeProvider` | `components/BackendWakeProvider.tsx` | Keeps Render free tier from sleeping |
| `ProtectedRoute` | `components/auth/ProtectedRoute.tsx` | Route guard component |

### Authentication Flow

```
User → Firebase Auth (email/password) → JWT Token → Session Cookie
     → middleware.ts checks cookie → Allow/Deny route access
     → X-User-UID header sent with API requests for user-scoped data
```

---

## 6. Backend Architecture

### Module Structure

```
backend/
├── api/
│   ├── main.py                    # FastAPI app, CORS, middleware, router registration
│   └── routers/
│       ├── sessions.py            # Session CRUD (POST /sessions/, GET /sessions/{id})
│       ├── ingest.py              # File upload, demo dataset, raw JSON ingestion
│       ├── review.py              # Chunk listing + restore noise items
│       ├── brd.py                # BRD generation, export, SSE stream, section editing
│       ├── hitl.py               # Human-in-the-loop ad-hoc prompt
│       └── slack.py              # Slack OAuth + channel ingestion
│
├── brd_module/
│   ├── brd_pipeline.py           # Multi-agent orchestrator (7 agents, 3 phases)
│   ├── validator.py              # Gap + contradiction validation (rule-based + LLM)
│   ├── exporter.py               # md / html / docx / pdf export
│   ├── storage.py                # PostgreSQL + SQLite database abstraction layer
│   ├── schema.py                 # Pydantic models (ClassifiedChunk, SignalLabel)
│   ├── adk_agents.py             # Google ADK agent definitions
│   ├── adk_config.py             # ADK configuration (model, session service)
│   ├── adk_workflow.py           # ADK workflow graph builder
│   ├── adk_orchestrator.py       # ADK orchestration with iterative refinement
│   └── hitl/
│       ├── versioned_ledger.py   # Section lock + version history
│       └── orchestrator.py       # Ad-hoc prompt handler
│
├── Noise filter module/
│   ├── classifier.py             # Two-phase classification engine
│   ├── prompts.py                # LLM prompt templates for classification
│   ├── schema.py                 # Classification-specific Pydantic models
│   ├── storage.py                # Noise filter storage operations
│   ├── enron_parser.py           # Enron email dataset parser
│   └── main.py                   # Standalone entry point
│
└── Integration Module/
    ├── gmail.py                  # Gmail API integration
    ├── slack_auth.py             # Slack authentication helpers
    ├── pdf.py                    # PDF/DOCX text extraction
    ├── ocr.py                    # Google Cloud Vision OCR
    ├── state.py                  # Integration state management
    └── routes/
        ├── gmail_routes.py       # Gmail REST endpoints
        ├── pdf_routes.py         # PDF processing endpoints
        └── slack_routes.py       # Additional Slack endpoints
```

### CORS & Middleware

The backend implements a **dual CORS strategy**:
1. **Standard CORSMiddleware** — handles preflight & response headers correctly
2. **Custom `cors_header_injector` middleware** — safety net ensuring every response (including errors) carries CORS headers

Allowed origins include production frontend URL and common localhost ports (3000, 3001, 5173).

### Database Abstraction Layer

The `storage.py` module provides a **dual-database abstraction**:
- **PostgreSQL** (primary): Uses psycopg2 with `%s` parameter style, `RealDictCursor`, native `JSONB` and `UUID` types
- **SQLite** (fallback): Auto-activates when PostgreSQL is unreachable, uses `?` parameter style, `TEXT` for JSON/UUID

All queries are written in PostgreSQL syntax and automatically translated to SQLite compatible syntax via `replace("%s", "?")`.

---

## 7. AI/ML Pipeline

### 7.1 Noise Filter — Two-Phase Classification

```
Raw Text Chunks
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1 — Heuristic Gate (CPU-bound, no API calls)         │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  System Mail Patterns                                 │   │
│  │  (delivery status, out-of-office, auto-reply)        │   │
│  │  → NOISE (confidence: 1.0)                           │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Social Noise Patterns                                │   │
│  │  ("thanks", "sounds good", "ok", "got it")           │   │
│  │  → NOISE if word_count < 10                          │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Meeting/Scheduling Patterns                          │   │
│  │  (dial-in, webex, zoom, conference room)             │   │
│  │  → NOISE (strict) or NOISE if short (<50 words)      │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Project Timeline Patterns                            │   │
│  │  (deadline, milestone, go-live, code freeze)         │   │
│  │  → TIMELINE_REFERENCE (confidence: 1.0)              │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Domain Gate                                          │   │
│  │  Short (<10 words) + no signal nouns/verbs           │   │
│  │  → NOISE                                              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  Result: ~40-60% of chunks classified without LLM           │
└─────────────────────────────────────────────────────────────┘
      │ (unresolved chunks)
      ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2 — LLM Batch Classification                         │
│  (batch=10, 2 concurrent batches, rate-safe)                │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Groq API: meta-llama/llama-4-scout-17b-16e-instruct │   │
│  │  Temperature: 0.0 (deterministic)                     │   │
│  │  Response format: JSON                                │   │
│  │  Max retries: 5 with exponential backoff              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  Confidence Thresholding:                                    │
│  ≥ 0.85  → Auto-accept                                      │
│  0.55-0.84 → Accept + flag for review                       │
│  < 0.55  → Retain label + always flag for review            │
│                                                             │
│  Fallback: If LLM unavailable → local keyword classifier    │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
  ClassifiedChunk objects → stored in classified_chunks table
```

### 7.2 Signal Labels

| Label | Meaning | Example Keywords |
|-------|---------|-----------------|
| `requirement` | Functional/non-functional product requirement | must, should, need, require, system, feature |
| `decision` | Architectural or product decision | decided, approved, finalized, selected, agreed |
| `stakeholder_feedback` | Explicit feedback from a stakeholder | feedback, prefer, concern, issue, request, suggest |
| `timeline_reference` | Deadline, milestone, or phase reference | deadline, milestone, launch, go-live, phase |
| `noise` | System email, scheduling, chatter | (auto-detected) |

### 7.3 Multi-Agent BRD Generation Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                    BRD GENERATION PIPELINE                           │
│                                                                     │
│  Stage 0: Snapshot Creation                                         │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Freeze active signal chunk IDs → brd_snapshots table        │  │
│  │  Ensures reproducibility: same inputs = same outputs          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Phase 1 (Parallel — 3 agents, ThreadPoolExecutor max_workers=3)   │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐    │
│  │  FRD Agent       │ │  NFRD Agent      │ │  Stakeholder     │    │
│  │  (functional_    │ │  (nfrd)          │ │  Agent           │    │
│  │   requirements)  │ │                  │ │  (stakeholder_   │    │
│  │                  │ │  Input: NFRD     │ │   analysis)      │    │
│  │  Input:          │ │  keywords +      │ │                  │    │
│  │  requirement     │ │  decision signals│ │  Input: All      │    │
│  │  signals         │ │                  │ │  signals         │    │
│  │                  │ │  Categories:     │ │                  │    │
│  │  Output:         │ │  Performance,    │ │  Output:         │    │
│  │  FR-001..N       │ │  Security,       │ │  Stakeholder     │    │
│  │  with priority,  │ │  Scalability,    │ │  table +         │    │
│  │  acceptance      │ │  Usability,      │ │  analysis        │    │
│  │  criteria, deps  │ │  Compliance,     │ │                  │    │
│  │                  │ │  Availability    │ │                  │    │
│  └────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘    │
│           │                    │                     │              │
│           └────────────────────┼─────────────────────┘              │
│                                │                                    │
│  Phase 2 (Parallel — 4 agents, with Phase 1 context)               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌───────────┐  │
│  │  Timeline    │ │  Business    │ │  Assumptions │ │  Success  │  │
│  │  Agent       │ │  Rules Agent │ │  & Risks     │ │  Metrics  │  │
│  │  (timeline)  │ │  (decisions) │ │  Agent       │ │  Agent    │  │
│  │              │ │              │ │  (assumptions│ │  (success_│  │
│  │  Input:      │ │  Input:      │ │  _risks)     │ │  metrics) │  │
│  │  timeline_   │ │  decision    │ │              │ │           │  │
│  │  reference   │ │  signals     │ │  Input: All  │ │  Input:   │  │
│  │  signals     │ │              │ │  signals     │ │  require- │  │
│  │              │ │  Output:     │ │              │ │  ment +   │  │
│  │  Output:     │ │  BR-001..N   │ │  Output:     │ │  decision │  │
│  │  Chrono-     │ │  with rule   │ │  A-001..N    │ │  signals  │  │
│  │  logical     │ │  statement,  │ │  assumptions │ │           │  │
│  │  milestones  │ │  category,   │ │  R-001..N    │ │  Output:  │  │
│  │              │ │  enforcement │ │  risks with  │ │  SM-001..N│  │
│  │              │ │              │ │  mitigation  │ │  with     │  │
│  │              │ │              │ │              │ │  targets  │  │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └─────┬─────┘  │
│         │                │                │               │         │
│         └────────────────┴────────────────┴───────────────┘         │
│                              │                                      │
│  Phase 3a: Executive Summary (sequential — reads all 6 outputs)     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Reads all Phase 1 + Phase 2 outputs from DB                  │  │
│  │  Generates 3-5 paragraph executive summary                    │  │
│  │  Includes honest completeness statement                       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│  Phase 3b: Validation Agent                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  1. Rule-based completeness checks (section length, gaps)     │  │
│  │  2. Rule-based cross-section checks (orphan metrics, risks)   │  │
│  │  3. LLM-powered semantic validation (contradictions)          │  │
│  │  → Stores flags in brd_validation_flags table                 │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.4 LLM Configuration

| Parameter | Value |
|-----------|-------|
| **Classification Model** | `meta-llama/llama-4-scout-17b-16e-instruct` |
| **Generation Model** | `llama-3.3-70b-versatile` (configurable via `GROQ_MODEL` env var) |
| **Temperature** | 0.0 (deterministic outputs) |
| **Max Tokens** | 2048 |
| **Retry Strategy** | 3 attempts with exponential backoff |
| **JSON Mode** | Enabled for classification; disabled for generation |
| **Rate Limiting** | Batch size 10, 2 concurrent batches, 1s sleep between groups |

### 7.5 ADK Orchestration (Alternative Engine)

When `USE_ADK_ORCHESTRATOR=true`, the system uses Google's Agent Development Kit instead of the ThreadPoolExecutor pipeline:

```
Round 0: All 7 section agents run in parallel → Executive Summary → Validation
Round 1+: If conflicts found → re-run ONLY conflicting sections with conflict context → Re-validate
Max refinement rounds: 2
```

The ADK path provides:
- **Iterative refinement**: Automatically detects and fixes conflicts
- **Better agent coordination**: ADK's workflow graph manages dependencies
- **Session state management**: All agents share state through ADK's InMemorySessionService

---

## 8. Database Design

### Entity-Relationship Diagram

```
┌──────────────────────┐       ┌──────────────────────┐
│   classified_chunks  │       │    brd_snapshots     │
├──────────────────────┤       ├──────────────────────┤
│ chunk_id (PK, UUID)  │       │ snapshot_id (PK,UUID)│
│ session_id (VARCHAR) │       │ session_id (VARCHAR) │
│ source_ref (VARCHAR) │       │ created_at (TIMESTAMP│
│ label (VARCHAR)      │       │ chunk_ids (JSONB)    │
│ suppressed (BOOLEAN) │       └──────────┬───────────┘
│ manually_restored    │                  │
│ flagged_for_review   │                  │ 1:N
│ created_at (TIMESTAMP│                  ▼
│ data (JSONB)         │       ┌──────────────────────┐
└──────────────────────┘       │    brd_sections      │
                               ├──────────────────────┤
                               │ section_id (PK, UUID)│
                               │ session_id (VARCHAR) │
                               │ snapshot_id (FK)     │
                               │ section_name (VARCHAR│
                               │ version_number (INT) │
                               │ content (TEXT)       │
                               │ source_chunk_ids(JSON│
                               │ is_locked (BOOLEAN)  │
                               │ human_edited (BOOLEAN│
                               │ generated_at (TS)    │
                               │ data (JSONB)         │
                               └──────────┬───────────┘
                                          │ 1:N
                                          ▼
                               ┌──────────────────────┐
                               │ brd_validation_flags │
                               ├──────────────────────┤
                               │ flag_id (PK, UUID)   │
                               │ session_id (VARCHAR) │
                               │ section_name (VARCHAR│
                               │ flag_type (VARCHAR)  │
                               │ description (TEXT)   │
                               │ severity (VARCHAR)   │
                               │ auto_resolvable (BOOL│
                               │ created_at (TS)      │
                               └──────────────────────┘
```

### Firestore Collections (Frontend Collaboration)

```
boards/{boardId}
  ├── name: string
  ├── ownerId: string
  ├── createdAt: timestamp
  └── members/{uid}
       ├── role: "owner" | "editor" | "viewer"
       └── joinedAt: timestamp

users/{uid}
  └── boards/{boardId}
       └── role: string

invites/{token}
  ├── boardId: string
  ├── role: "editor" | "viewer"
  ├── createdAt: timestamp
  └── expiry: timestamp (24h TTL)
```

### Database Tables Detail

#### `classified_chunks`
Stores every ingested and classified text chunk. The `data` JSONB column contains the full Pydantic model serialization for reconstruction.

#### `brd_snapshots`
Immutable snapshots of which chunk IDs were used for a BRD generation run. Ensures reproducibility.

#### `brd_sections`
Versioned BRD sections. Each edit (AI or human) creates a new version. The `is_locked` flag (via `human_edited`) prevents AI from overwriting approved content.

#### `brd_validation_flags`
Quality flags generated by the validator. Types: `gap`, `conflict`, `orphan`, `coverage`, `contradiction`. Severities: `high`, `medium`, `low`.

---

## 9. API Reference

### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sessions/` | Create a new BRD session → returns `session_id` |
| `GET` | `/sessions/{id}` | Get session status |

### Ingestion

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sessions/{id}/ingest/data` | Ingest raw JSON chunks |
| `POST` | `/sessions/{id}/ingest/upload` | Upload a file (.txt, .csv, .pdf, .docx) |
| `POST` | `/sessions/{id}/ingest/upload-ocr` | Upload PDF/image for OCR + ingestion |
| `POST` | `/sessions/{id}/ingest/demo?limit=80` | Stream-ingest Enron email demo dataset |

### Signal Review

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/sessions/{id}/chunks?status=signal\|noise\|all` | List classified chunks |
| `POST` | `/sessions/{id}/chunks/{chunk_id}/restore` | Restore suppressed chunk to active |
| `DELETE` | `/sessions/{id}/chunks/?source_ref_prefix=...` | Delete chunks by source prefix |

### BRD Generation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sessions/{id}/brd/generate` | Synchronous generation (ThreadPoolExecutor or ADK) |
| `GET` | `/sessions/{id}/brd/generate/stream` | SSE streaming with real-time agent progress |
| `GET` | `/sessions/{id}/brd/` | Get latest BRD sections + meta + validation flags |
| `PUT` | `/sessions/{id}/brd/sections/{name}` | Human edit + lock a section |
| `POST` | `/sessions/{id}/brd/sections/{name}/generate` | Regenerate a single section |
| `POST` | `/sessions/{id}/brd/approve` | Approve all validation flags |
| `GET` | `/sessions/{id}/brd/sections/{name}/history` | Get version history of a section |
| `GET` | `/sessions/{id}/brd/export?format=markdown\|html\|docx\|pdf` | Export BRD |

### HITL

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sessions/{id}/hitl/prompt` | Submit ad-hoc prompt to refine a section |

### Slack Integration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/integrations/slack/auth/start` | Start Slack OAuth flow |
| `GET` | `/integrations/slack/auth/callback` | OAuth callback |
| `GET` | `/integrations/slack/status` | Check connection status |
| `POST` | `/integrations/slack/disconnect` | Disconnect Slack |
| `GET` | `/integrations/slack/channels` | List accessible channels |
| `POST` | `/integrations/slack/ingest` | Ingest messages from channels |

### Gmail Integration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/integrations/gmail/auth/start` | Start Gmail OAuth flow |
| `GET` | `/integrations/gmail/auth/callback` | OAuth callback |
| `GET` | `/integrations/gmail/status` | Check connection status |
| `POST` | `/integrations/gmail/disconnect` | Disconnect Gmail |
| `GET` | `/integrations/gmail/check` | List/search emails |
| `POST` | `/integrations/gmail/ingest` | Ingest selected emails |

### Health & Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Root health check |
| `GET` | `/healthz` | Detailed health with uptime |
| `GET` | `/wake` | Wake-up endpoint for Render free tier |

---

## 10. Security Architecture

### Authentication
- **Firebase Authentication** with email/password
- Session cookies (`firebase-session`) set via Next.js API route `/api/auth/session`
- Cookie-based route protection via Next.js middleware
- `X-User-UID` header sent with API requests for user-scoped backend operations

### Authorization
- **Frontend**: `ProtectedRoute` component + middleware.ts route guard
- **Backend**: User-scoped data via `X-User-UID` header
- **Board sharing**: Role-based (owner/editor/viewer) via Firestore security rules

### CORS
- Dual-layer CORS: CORSMiddleware + custom header injector
- Credentials allowed
- Origin whitelist with localhost wildcard support

### Environment Variables

**Backend (required):**
| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` / `GROQ_CLOUD_API` | LLM API access |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` | PostgreSQL connection |
| `BACKEND_PUBLIC_URL` | Slack OAuth redirect construction |
| `FRONTEND_URL` | Post-OAuth redirect |
| `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET` | Slack OAuth (optional) |
| `CRON_HEALTH_TOKEN` | Health check auth (optional) |

**Frontend (required):**
| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | Backend base URL |
| `NEXT_PUBLIC_FIREBASE_*` | Firebase client config (6 vars) |
| `FIREBASE_ADMIN_*` | Firebase Admin SDK (3 vars, server-only) |

---

## 11. Deployment Architecture

### Production Deployment

```
┌─────────────────────────────────────────────────────────────┐
│                     VERCEL (Frontend)                        │
│  - Next.js 14 App Router                                    │
│  - Automatic SSL, CDN, edge network                         │
│  - Environment variables set in dashboard                   │
│  - Root directory: frontend/                                │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS
┌────────────────────────┴────────────────────────────────────┐
│                     RENDER (Backend)                         │
│  - Docker container from backend/Dockerfile                 │
│  - Python 3.11-slim-bookworm base image                     │
│  - Uvicorn on port 8080                                     │
│  - Auto-deploy on git push                                  │
│  - Free tier: sleeps after 15min inactivity                 │
│  - /wake endpoint for keep-alive                            │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Render       │ │  Firebase    │ │  Groq Cloud  │
│  PostgreSQL   │ │  Auth +      │ │  LLM API     │
│  (or Supabase/│ │  Firestore   │ │              │
│   Neon)       │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
```

### Docker Configuration

```dockerfile
FROM python:3.11-slim-bookworm
# System deps: build-essential, libpq-dev, Cairo/Pango (WeasyPrint)
# Python deps: requirements.txt
# Port: 8080
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Local Development

```powershell
# One-command launch (Windows)
.\start-dev.ps1

# Manual:
# Terminal 1: cd backend → uvicorn api.main:app --reload --port 8000
# Terminal 2: cd frontend → npm run dev
# Open: http://localhost:3000
```

---

## 12. Data Flow Diagrams

### Complete User Flow

```
User opens Beacon
       │
       ▼
[Landing Page] ──Register──▶ [Firebase Auth] ──▶ [Session Cookie Set]
       │                                         │
       └────────────Login────────────────────────┘
                          │
                          ▼
                   [Dashboard]
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        [Create New]  [Select      [Join via
         Session]     Session]     Invite Link]
              │           │           │
              └───────────┼───────────┘
                          │
                          ▼
                   [Ingestion Page]
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
   [Upload File]   [Connect Slack]   [Run Enron Demo]
   .txt/.csv/.docx   OAuth flow       Streaming ingest
   PDF (+OCR)        Channel select   with live log
         │                │                │
         └────────────────┼────────────────┘
                          │
                          ▼
              [Noise Filter Pipeline]
              Phase 1: Heuristics (CPU)
              Phase 2: LLM Batch (API)
                          │
                          ▼
                   [Signals Page]
                   Review active signals
                   Restore misclassified noise
                          │
                          ▼
                [Generate BRD Button]
                          │
                          ▼
              [BRD Generation Pipeline]
              Phase 1: FRD + NFRD + Stakeholder (parallel)
              Phase 2: Timeline + Rules + Risks + Metrics (parallel)
              Phase 3: Executive Summary → Validation
                          │
                    (SSE streaming)
                          │
                          ▼
                [BRD Review Page]
                Read section cards
                Review validation flags
                Edit sections (HITL)
                Lock approved sections
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
         [Export]   [Share Board]  [Approve]
         .md/.html   Invite link    Clear flags
         .docx/.pdf  Role assign
```

### SSE Streaming Protocol

The backend streams real-time agent progress via Server-Sent Events:

```
event: generation_started    → { session_id }
event: snapshot_created      → { session_id, snapshot_id }
event: agents_launched       → { session_id, count, phase }
event: agent_started         → { session_id, agent }
event: agent_completed       → { session_id, agent }
event: agent_failed          → { session_id, agent, error }
event: validation_started    → { session_id }
event: validation_completed  → { session_id }
event: generation_completed  → { session_id, snapshot_id }
event: complete              → { session_id, snapshot_id, message }
event: error                 → { session_id, message }
```

---

## 13. Feature Deep-Dive

### 13.1 Multi-Source Ingestion

| Source | Method | Processing |
|--------|--------|------------|
| **File Upload** | `POST /ingest/upload` (multipart) | Text extraction → chunking (~1500 chars) → classification |
| **OCR Upload** | `POST /ingest/upload-ocr` | Google Cloud Vision OCR → chunking → classification |
| **Slack** | `POST /integrations/slack/ingest` | Fetch messages → strip formatting → chunking → classification |
| **Gmail** | `POST /integrations/gmail/ingest` | Fetch emails → extract body → chunking → classification |
| **Raw JSON** | `POST /ingest/data` | Direct chunk ingestion → classification |
| **Enron Demo** | `POST /ingest/demo` | Parse emails.csv → streaming classification with live log |

**Chunking Strategy:**
- Split on double newlines (paragraphs)
- Target ~1500 chars per chunk
- Fall back to sentence splitting for long paragraphs
- Preserve source reference metadata

### 13.2 Human-in-the-Loop (HITL)

The HITL system allows users to:
1. **Edit any section** — `PUT /brd/sections/{name}` stores human content with `human_edited=true`
2. **Lock sections** — When `human_edited=true`, agents skip re-generation for that section
3. **Version history** — Every edit creates a new version; full history retrievable via `GET /brd/sections/{name}/history`
4. **Ad-hoc prompts** — `POST /hitl/prompt` for natural language section refinement
5. **Approve flags** — `POST /brd/approve` clears all validation flags

### 13.3 Multi-Format Export

| Format | Method | Details |
|--------|--------|---------|
| **Markdown** | `export_brd()` | Compiled from sections + validation flags |
| **HTML** | Inline generation | Styled HTML with embedded CSS, section cards |
| **DOCX** | `export_brd_to_docx()` | Template-based (`brd.docx`) or from-scratch with full markdown parsing |
| **PDF** | `export_brd_to_pdf()` | WeasyPrint: Markdown → HTML → PDF with professional styling |

**DOCX Export Features:**
- Template-based: Replaces `{TITLE}`, `{EXECUTIVE_SUMMARY}`, etc. in a Word template
- From-scratch: Full markdown parser supporting headings, bold, italic, code, tables, lists, blockquotes, links, strikethrough
- Professional styling: Blue theme, alternating table rows, code blocks with Consolas font

### 13.4 Team Collaboration

- **Board creation** with owner role
- **Invite links** with 24-hour TTL
- **Role-based access**: Owner, Editor, Viewer
- **Firestore-backed** for real-time sync
- **Reverse index** (`users/{uid}/boards/{boardId}`) for dashboard listing

### 13.5 Signal Traceability

Every BRD section maintains:
- `source_chunk_ids`: UUIDs of the classified chunks that contributed to the section
- `snapshot_id`: The frozen snapshot of signals used for the generation run
- `version_number`: Incrementing version for audit trail
- Full chunk data retrievable via section history endpoint

### 13.6 Graceful Degradation

| Failure Mode | Fallback |
|--------------|----------|
| PostgreSQL unreachable | SQLite auto-activation |
| Groq API unavailable | Local keyword classifier |
| WeasyPrint unavailable | PDF export returns 503 with message |
| python-docx unavailable | DOCX export returns ImportError |
| Slack SDK missing | Returns 500 with descriptive message |
| Enron CSV missing | Synthetic demo data (7 rotating messages) |

---

## 14. Project Rating & Honest Assessment

### Overall Rating: 3.8 / 5 ⭐⭐⭐⭐

---

### Strengths (What's genuinely impressive)

**1. AI Pipeline Architecture — 4.5/5**
The two-phase noise filter is genuinely clever. Using heuristics to classify 40-60% of chunks without LLM calls shows real engineering thinking about cost optimization. The 3-phase agent pipeline with proper dependency management (Phase 2 reads Phase 1 output, Phase 3 reads everything) demonstrates solid orchestration design.

**2. Graceful Degradation — 4.5/5**
This is one of the strongest aspects. SQLite fallback, heuristic fallback, optional modules — the system is designed to work even when components fail. This is production-minded thinking.

**3. Export System — 4/5**
The DOCX export with full markdown parsing (handling nested formatting, tables, code blocks, links, strikethrough) is remarkably thorough. The template-based approach with fallback to from-scratch generation is well-designed.

**4. Real-time UX — 4/5**
SSE streaming of agent progress with typed events provides a polished user experience. The `BackendWakeProvider` for Render free tier shows attention to deployment realities.

**5. HITL Design — 4/5**
Versioned ledger with section locking, full history retrieval, and ad-hoc prompts creates a proper human-AI collaboration loop.

---

### Weaknesses (Honest critique)

**1. Testing — 1.5/5**
This is the biggest gap. Only one test file exists (`test_wake.py`). There are no tests for:
- The noise filter classifier
- The BRD generation pipeline
- The validator
- The exporter
- The database layer
- Any API endpoint
- The ingestion pipeline

For a system this complex, the absence of tests is a significant risk. One wrong regex change in the heuristic filter could silently misclassify thousands of chunks.

**2. Error Handling — 2.5/5**
While graceful degradation exists, many endpoints use bare `except Exception` blocks that swallow errors silently. The `store_validation_flag` function in `validator.py` doesn't handle DB errors. The Slack ingestion catches `SlackApiError` but re-raises as a generic 500 without structured error responses.

**3. Authentication on Backend — 2.5/5**
The backend relies on `X-User-UID` header passed from the frontend, which is trivially spoofable. There's no server-side JWT verification on the backend. The Slack/Gmail OAuth state management uses in-memory dictionaries (`_oauth_states`, `_slack_credentials`) which won't work with multiple workers/processes and loses state on restart.

**4. Database Design — 3/5**
- No proper sessions table (sessions are just UUIDs with no metadata)
- The `data` JSONB column stores full serialized Pydantic models, creating data duplication with the indexed columns
- No foreign key constraints (even in PostgreSQL) between snapshots and sections
- No indexes on frequently queried columns (e.g., `brd_sections.session_id`, `brd_validation_flags.session_id`)
- The `is_locked` concept is conflated with `human_edited` — a section could be human-edited but the user might want the AI to still regenerate it

**5. Code Organization — 3/5**
- The `brd_module/storage.py` has an unused `execute_query` function with a confusing API
- The `Noise filter module` directory has a space in its name, causing import gymnastics (`sys.path` manipulation)
- The integration module has duplicate Gmail routes (legacy + new)
- Some functions are very long (e.g., `export_brd_to_docx` at 980 lines, `brd_pipeline.py` at 766 lines)
- The ADK orchestrator imports `os` without importing it at the module level (`adk_orchestrator.py` line 22)

**6. Frontend — 3.5/5**
- The UI component library (Framer Motion, Radix UI, custom components) is solid
- However, many pages are stubs (analytics, templates, agents) with minimal functionality
- No error boundaries or loading states in many components
- The Zustand store directly calls API functions without a service layer abstraction
- No optimistic updates for most mutations

**7. DevOps & CI/CD — 2/5**
- No CI/CD pipeline configured
- No linting configuration for the backend (no flake8, mypy, or black)
- No staging environment
- The Dockerfile doesn't use multi-stage builds, resulting in a larger image
- No health check configured in Docker

**8. Documentation — 3.5/5**
- The README is comprehensive and well-structured
- API docs via Swagger UI at `/docs` (FastAPI auto-generated)
- However, no inline code documentation for complex functions
- No architecture decision records (ADRs)
- No contribution guidelines beyond basic setup

---

### What Would Push This to a 4.5/5

1. **Comprehensive test suite** — Unit tests for all modules, integration tests for API endpoints, end-to-end tests for the full pipeline
2. **Proper backend auth** — Firebase Admin SDK verification of JWT tokens on every request
3. **Database migrations** — Alembic or similar for schema versioning
4. **Structured logging** — Replace print statements with proper logging framework
5. **CI/CD pipeline** — GitHub Actions for linting, testing, and deployment
6. **Complete frontend pages** — Analytics, templates, and agents pages need real functionality
7. **Rate limiting** — API rate limiting to prevent abuse
8. **Monitoring** — Application performance monitoring (e.g., Sentry, Datadog)

---

### Summary

Beacon is a **genuinely impressive full-stack project** that solves a real business problem with thoughtful AI pipeline engineering. The two-phase noise filter, graceful degradation, and multi-format export system demonstrate strong technical thinking. The architecture is clean and well-separated.

The main gaps are in **testing, security hardening, and production readiness** — the areas that separate a hackathon project from a production system. The core AI pipeline and system design are strong enough that with proper testing, auth, and DevOps, this could be a legitimate product.

**For a freelancer evaluating this:** The codebase shows strong Python/FastAPI skills, good understanding of LLM orchestration, and solid frontend architecture. The main areas needing investment are testing, security, and DevOps.

**For a UI/UX designer evaluating this:** The frontend has a solid foundation with Tailwind CSS, Framer Motion animations, and Radix UI primitives. The SSE streaming UX for agent progress is a standout feature. The main opportunity is completing the analytics dashboard, templates system, and agent visualizer — these pages exist as routes but need full UI implementation.

---

*Document generated by OWL — ZOO Company*  
*Last updated: June 13, 2026*
