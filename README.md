# Arab Bank AI Loan Advisor

An intelligent, full-stack loan advisory system that combines conversational AI with retrieval-augmented generation (RAG) and deterministic credit-risk scoring. Customers interact through a branded chat interface, ask questions about loan policies, and receive real-time eligibility decisions — all driven by a single-agent architecture orchestrated with LangGraph.

Built as a production-grade prototype for Arab Bank, the system demonstrates how agentic AI can sit at the center of a lending workflow: understanding intent, pulling customer data and market signals, retrieving relevant policy passages, scoring risk, and explaining decisions in plain language.

---

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Scripts & Utilities](#scripts--utilities)
- [License](#license)

---

## Features

**Conversational AI**
- Natural-language chat interface for loan inquiries and eligibility checks
- 10-turn conversation memory so the assistant maintains context across messages
- Intent classification (greeting, policy question, eligibility check) drives what the agent does next

**Retrieval-Augmented Generation (RAG)**
- Policy documents are chunked, embedded with OpenAI `text-embedding-3-small`, and indexed in Qdrant
- When a customer asks about terms, rates, or requirements, the system retrieves the most relevant policy passages and grounds its answer in them
- Every response includes clickable source references (S1, S2, S3…) so the customer can trace claims back to policy text

**Credit-Risk Scoring**
- Composite risk score built from customer profile data (income, employment, existing debt, risk grade), live market metrics, and a bank health constant
- Configurable thresholds for APPROVE / COUNTER / DECLINE decisions
- Market data scraped on a cron schedule from public economic sources (FRED, BLS, real estate indices)

**Agentic Orchestration**
- LangGraph state-machine workflow with named nodes: guardrail → intent → data gathering → scoring → judge → serializer
- A single-agent controller that plans, fetches data, reasons, and decides — with iteration limits and confidence tracking
- LLM judge layer (GPT-4o-mini) that validates every decision before it reaches the customer

**Safety & Guardrails**
- Input and output guardrail nodes that run OpenAI's Moderation API plus regex-based forbidden-term detection
- Off-topic or harmful queries are refused gracefully without leaking internal state
- All decisions are audited in an `audit_log` table with full state snapshots

**Production Concerns**
- JWT authentication with PBKDF2-hashed passwords
- Request-ID tracking and structured logging across every node
- Rate limiting (SlowAPI), CORS configuration, and health-check endpoints for monitoring
- Incremental policy indexing (SHA-256 hash comparison) so re-indexing is fast

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     Next.js 14 Frontend                      │
│    Landing Page  ·  Login  ·  Chat Interface  ·  Sidebar     │
└──────────────┬───────────────────────────────────────────────┘
               │  REST API (JWT-authenticated)
               ▼
┌──────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                           │
│                                                              │
│  /v1/auth/login    →  JWT token issuance                     │
│  /v1/auth/refresh  →  Token refresh                          │
│  /v1/loan/decision →  Main conversation endpoint             │
│  /v1/loan/workflow-info → System capabilities                │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              LangGraph Workflow Engine                  │  │
│  │                                                        │  │
│  │  guardrail_in → intent_classifier → [data nodes] →     │  │
│  │  score_node → judge_and_explain → guardrail_out →      │  │
│  │  serializer                                            │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Customer │  │  Market   │  │  Policy  │  │   Chat     │  │
│  │   Data   │  │  Scraper  │  │   RAG    │  │  History   │  │
│  │ (SQLite) │  │ (SQLite)  │  │ (Qdrant) │  │ (SQLite)   │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

The frontend is a Next.js 14 app that proxies API calls to the FastAPI backend. The backend's `/decision` endpoint feeds every message through a LangGraph state machine. Depending on the classified intent, the graph conditionally activates data-fetching nodes (customer lookup, market metrics, policy RAG) before a scoring node and an LLM judge produce the final response.

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | Next.js (App Router) | 14.0.0 |
| UI Language | TypeScript | 5.x |
| Styling | Tailwind CSS | 3.3.0 |
| Animations | Framer Motion | 10.16.5 |
| Backend | FastAPI | 0.104.1 |
| ASGI Server | Uvicorn | 0.24.0 |
| Agent Framework | LangGraph | 0.1.9 |
| LLM | OpenAI GPT-4o-mini | via openai 1.3.7 |
| Embeddings | text-embedding-3-small | 1536 dims |
| Vector Store | Qdrant | client 1.9.0 |
| ORM | SQLAlchemy | 2.0.36 |
| Database | SQLite | built-in |
| Auth | PyJWT + PBKDF2 | 3.3.0 |
| Rate Limiting | SlowAPI | 0.1.9 |
| Scheduling | APScheduler | 3.10.4 |
| Validation | Pydantic | 2.7.4 |

---

## Project Structure

```
├── app/
│   ├── api/                 # FastAPI routes, auth, middleware, schemas
│   │   ├── main.py          # FastAPI app factory + health endpoints
│   │   ├── auth.py          # Login / refresh endpoints
│   │   ├── loan.py          # /decision and /workflow-info endpoints
│   │   ├── deps.py          # Dependency injection (DB, auth, request ID)
│   │   ├── schemas.py       # Pydantic request/response models
│   │   └── middleware.py    # Request tracking, CORS
│   │
│   ├── graph/               # LangGraph workflow definitions
│   │   ├── workflow.py      # Main graph: nodes + edges + conditional routing
│   │   ├── state.py         # TypedDict state schema
│   │   ├── intent.py        # Intent classification (pattern + LLM)
│   │   └── agent_nodes.py   # Autonomous agent planning & execution nodes
│   │
│   ├── nodes/               # Business-logic nodes
│   │   ├── single_agent.py  # Single-agent controller (memory, tools, LLM)
│   │   ├── guardrail.py     # Content safety (Moderation API + regex)
│   │   └── llm_judge.py     # Decision validation layer
│   │
│   ├── rag/                 # Retrieval-augmented generation
│   │   ├── retriever.py     # Qdrant similarity search
│   │   ├── index_policy.py  # Policy document indexer (incremental)
│   │   └── embeddings.py    # Embedding generation + caching
│   │
│   ├── scrape/              # Market data scrapers
│   │   ├── scheduler.py     # APScheduler cron jobs
│   │   ├── store.py         # SQLite market-data cache
│   │   ├── scrape_fred.py   # Federal Reserve data
│   │   ├── scrape_bls.py    # Bureau of Labor Statistics
│   │   └── ...              # Additional scrapers
│   │
│   ├── db/                  # Database layer
│   │   ├── database.py      # Engine, session management, migrations
│   │   ├── models.py        # Customer, AuditLog ORM models
│   │   └── chat_repo.py     # Chat message persistence
│   │
│   ├── mcp/                 # Model Context Protocol tool definitions
│   │   ├── schemas.py       # Input/output models for MCP tools
│   │   └── tools.py         # Tool wrappers (customer, market, policy, score)
│   │
│   ├── utils/               # Shared utilities
│   │   ├── config.py        # Pydantic settings (env + YAML)
│   │   ├── auth.py          # PBKDF2 hashing, JWT helpers
│   │   └── logger.py        # Structured logging setup
│   │
│   ├── components/          # React UI components
│   │   ├── ChatBubble.tsx   # Message display (user / assistant styling)
│   │   ├── HomeHero.tsx     # Landing page hero section
│   │   ├── Button.tsx       # Animated button component
│   │   └── ...              # Card, Input, Footer, Features, etc.
│   │
│   ├── context/             # React context providers
│   │   ├── AuthContext.tsx   # JWT auth state + login/logout
│   │   └── ChatContext.tsx   # Conversation state + message sending
│   │
│   ├── chat/page.tsx        # Chat interface page
│   ├── login/page.tsx       # Login page
│   ├── apply/page.tsx       # Loan application (placeholder)
│   ├── page.tsx             # Landing page
│   └── layout.tsx           # Root layout with providers
│
├── data/                    # Data files (gitignored: *.db)
│   ├── Clientbase_scored.csv
│   ├── policy_chunks.jsonl
│   └── policy_chunks_enriched.jsonl
│
├── docs/
│   └── data_dictionary.json # Schema documentation for client fields
│
├── scripts/                 # Setup, testing & verification scripts
│   ├── setup_db.py          # Initialize database tables
│   ├── load_customers.py    # Load customer CSV into SQLite
│   └── ...                  # Smoke tests, RAG verification, etc.
│
├── tests/                   # Pytest test suite
│   ├── test_api.py          # API endpoint tests
│   ├── test_auth.py         # Authentication tests
│   ├── test_graph.py        # Workflow graph tests
│   ├── test_guardrails.py   # Content safety tests
│   ├── test_nodes.py        # Node logic tests
│   ├── test_rag.py          # RAG retrieval tests
│   └── ...
│
├── config.yaml              # Application configuration
├── run_server.py            # Backend entry point
├── load_data.py             # Data loading utility
├── requirements.txt         # Python dependencies
├── package.json             # Node.js dependencies
└── .env.example             # Environment variable template
```

---

## Getting Started

### Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **Qdrant** — vector database ([installation guide](https://qdrant.tech/documentation/quick-start/))
- An **OpenAI API key** with access to `gpt-4o-mini` and `text-embedding-3-small`

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd agentic-rag

# Python backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

# Next.js frontend
npm install
```

### 2. Configure environment variables

Copy the template and fill in your values:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `JWT_SECRET` | A strong random string for signing JWT tokens |
| `DATABASE_URL` | SQLite connection string (default works out of the box) |

### 3. Start Qdrant

```bash
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

Or install and run Qdrant locally.

### 4. Initialize the database and index policies

```bash
# Create database tables and load customer data
python scripts/setup_db.py
python scripts/load_customers.py

# Index policy documents into Qdrant
python -c "from app.rag.index_policy import PolicyIndexer; PolicyIndexer().index()"
```

### 5. Start the backend

```bash
python run_server.py
```

The FastAPI server starts at `http://localhost:8000`. Swagger docs are available at `/docs`.

### 6. Start the frontend

```bash
npm run dev
```

Open `http://localhost:3000` in your browser. Log in with any customer ID from the database (password follows the pattern `password{id}` for demo purposes).

---

## Configuration

All settings live in `config.yaml` and can be overridden by environment variables. Key sections:

```yaml
database:
  url: "sqlite:///./data/app_new.db"    # Switch to PostgreSQL for production
  pool_size: 5

vector:
  host: "localhost"
  port: 6333
  collection_name: "policy_chunks"

llm:
  chat_model: "gpt-4o-mini"             # Primary LLM
  chat_fallback_model: "gpt-4o"         # Fallback on failure
  embedding_model: "text-embedding-3-small"
  temperature: 0.1

risk:
  hard_decline_threshold: 0.8           # Score above this → DECLINE
  approve_threshold: 0.65               # Score below this → APPROVE
  counter_threshold: 0.5                # Between thresholds → COUNTER

auth:
  algorithm: "HS256"
  access_token_expire_minutes: 1440     # 24 hours

rate_limit:
  requests_per_minute: 30

scrape:
  schedule_cron: "0 8,14 * * *"         # Market data refresh at 8 AM and 2 PM
```

---

## How It Works

### Conversation Flow

1. **User sends a message** through the chat UI
2. The frontend calls `POST /v1/loan/decision` with the question and JWT token
3. The backend's **single-agent controller** loads the last 10 messages for context
4. **Intent classification** decides what kind of question this is:
   - **ACK** — a greeting or acknowledgment → warm welcome response
   - **INFO** — a policy or product question → RAG retrieval + grounded answer
   - **ELIGIBILITY** — a loan qualification question → full data gathering + risk scoring
5. The LangGraph workflow activates the appropriate nodes:
   - **Guardrail In** checks for harmful or off-topic content
   - **Data nodes** fetch customer profile, market metrics, and/or policy snippets
   - **Score node** computes a composite risk score (for eligibility)
   - **Judge node** (GPT-4o-mini) produces the final answer and validates the decision
   - **Guardrail Out** checks the response before sending it back
6. The response includes the answer text, decision label, source references, and suggested quick replies

### Intent Classification

The system uses a two-stage classifier:
- **Heuristic pass** — regex patterns and keyword matching with confidence scoring
- **LLM judge pass** — if heuristic confidence is low, GPT-4o-mini arbitrates using the conversation context

This avoids burning LLM tokens on obvious intents while still handling ambiguous queries well.

### RAG Pipeline

Policy documents (JSONL format) are processed through:
1. **Chunking** — documents split into overlapping sections
2. **Embedding** — each chunk embedded with `text-embedding-3-small` (1536 dimensions)
3. **Indexing** — stored in Qdrant with metadata (section name, page number, source)
4. **Retrieval** — at query time, the user's question is embedded and the top-k similar chunks are returned
5. **Grounding** — the LLM generates its answer using only the retrieved policy text

Incremental indexing uses SHA-256 hashing of the source file, so unchanged documents are skipped on re-index.

### Risk Scoring

For eligibility questions, the system computes a weighted composite score:

```
score = (client_weight × client_risk) + (market_weight × market_risk) + (bank_weight × bank_health)
```

Where:
- **Client risk** is derived from income, employment, existing debt, past defaults, and risk grade (A–D)
- **Market risk** comes from scraped economic indicators (interest rates, CPI, real estate indices)
- **Bank health** is a configurable constant representing institutional risk appetite

The score maps to a decision via configurable thresholds.

---

## API Reference

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/auth/login` | Authenticate with customer ID and password; returns JWT tokens |
| POST | `/v1/auth/refresh` | Refresh an expired access token |

### Loan Operations

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/v1/loan/decision` | Bearer JWT | Send a message and receive an AI-driven loan response |
| GET | `/v1/loan/workflow-info` | Bearer JWT | Get available workflow modes and capabilities |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System health check (database, vector store, RAG) |

### Decision Response Shape

```json
{
  "decision": "INFORM",
  "answer": "Based on our lending policy, personal loan interest rates start at...",
  "references": [
    {"source": "S1", "section": "Interest Rates", "page": 3}
  ],
  "quick_replies": [
    {"label": "What are the eligibility requirements?"},
    {"label": "How do I apply?"}
  ],
  "cta": {"text": "Apply Now", "action": "apply_now"},
  "request_id": "REQ-a1b2c3d4",
  "processing_time_ms": 1200,
  "metadata": { ... }
}
```

Possible `decision` values: `APPROVE`, `COUNTER`, `DECLINE`, `INFORM`, `REFUSE`, `ACK`

---

## Testing

The project includes a Pytest test suite covering API endpoints, authentication, workflow graph logic, guardrails, RAG retrieval, and more.

```bash
# Run the full test suite
pytest tests/ -v

# Run a specific test module
pytest tests/test_auth.py -v
pytest tests/test_guardrails.py -v
```

---

## Scripts & Utilities

| Script | Purpose |
|--------|---------|
| `scripts/setup_db.py` | Create database tables |
| `scripts/load_customers.py` | Import customer CSV into SQLite |
| `scripts/start_qdrant_and_index.ps1` | Start Qdrant + index policy documents |
| `scripts/verify_rag_setup.py` | Verify RAG pipeline is working end-to-end |
| `scripts/smoke_test.py` | Quick smoke test of all API endpoints |
| `scripts/rag_verify.py` | Detailed RAG retrieval verification |
| `scripts/memory_transcript.py` | Test conversation memory continuity |
| `scripts/eligibility_no_hedge.py` | Verify eligibility decisions are decisive |

---

## 🔧 Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run ESLint

## 🎭 Mock Data

The application includes:
- Simulated authentication (any credentials work)
- Mock conversation history in sidebar
- Automated bot responses based on keywords
- Realistic loading states and animations

## 📱 Responsive Design

The interface adapts to different screen sizes:
- **Desktop:** Full sidebar and chat layout
- **Tablet:** Condensed sidebar
- **Mobile:** Collapsible navigation

---

Built with ❤️ for Arab Bank Digital Experience 
