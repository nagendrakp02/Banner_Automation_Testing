# Banner Automation Testing

Automated FDA compliance testing for pharmaceutical HTML5 banner advertisements.
Runs 7 checks per banner using Playwright browser automation and a local Vision AI (Ollama).

---

## Project Structure

```
bannermind_v10_vision_updated/
├── backend/
│   ├── main.py                     # FastAPI app entry point
│   ├── requirements.txt            # Python dependencies
│   ├── core/
│   │   ├── config.py               # Settings loaded from .env
│   │   └── constants.py            # Enums: CheckID, AgentName, CheckStatus
│   ├── db/
│   │   ├── models.py               # SQLAlchemy models: Banner, TestRun, CheckResult
│   │   └── session.py              # Async DB engine and session factory
│   ├── api/
│   │   ├── routes.py               # REST endpoints + WebSocket /ws/runs/{id}
│   │   └── health.py               # GET /health
│   ├── agents/
│   │   ├── base_agent.py           # BaseAgent abstract class + QA persona
│   │   ├── specialist_agents.py    # RenderAgent, VisualAgent, InteractionAgent, PerformanceAgent
│   │   ├── isi_agent.py            # ISIAgent: auto_scroll, text_layout, wheel_scroll
│   │   └── orchestrator_agent.py   # Coordinates the full test run
│   └── services/
│       ├── vision_client.py        # Ollama HTTP client with streaming + base64 images
│       ├── screenshot.py           # Playwright screenshot helpers
│       └── broadcaster.py          # WebSocket pub/sub for live log streaming
│
├── frontend/
│   └── src/
│       ├── App.tsx                 # Router
│       ├── pages/
│       │   ├── DashboardPage.tsx   # Overview stats
│       │   ├── BannersPage.tsx     # Banner registry
│       │   ├── RunsPage.tsx        # All test runs
│       │   └── RunDetailPage.tsx   # Live log + results
│       ├── components/
│       │   ├── ui/                 # StatusBadge, AgentBadge, Spinner
│       │   ├── runs/LogTerminal.tsx
│       │   └── results/CheckResultCard.tsx
│       ├── hooks/useRunLogs.ts     # WebSocket live log hook
│       ├── lib/api.ts              # Axios API functions
│       └── types/index.ts          # TypeScript interfaces
│
└── scripts/
    └── seed.py                     # Insert sample banners into DB
```

---

## The 7 Compliance Checks

| Check | What It Tests | Pass Condition |
|-------|--------------|----------------|
| Banner Visible | Banner renders without errors | `visibleElements > 0`, no blank page |
| Border Detected | Clear visual boundary around banner | CSS border or distinct background found |
| Copy Selection Disabled | Text cannot be selected or copied | `user-select: none` OR `Ctrl+A` selects 0 chars |
| Banner Load Time | Page loads fast enough | `loadMs ≤ 60,000ms` |
| ISI Auto-Scroll | Safety info scrolls automatically | ISI moves during 16s observation window |
| ISI Text Layout | Safety text is readable | No element bounding-box overlaps |
| ISI Wheel Scroll | User can scroll safety info with mouse | ISI moves on wheel event, no page scroll leak |

---

## Requirements

| Tool | Version | Required For |
|------|---------|-------------|
| Windows 10/11 | 22H2+ | OS |
| Python | 3.11 or 3.12 | Backend |
| Node.js | 18 LTS or 20 LTS | Frontend |
| Ollama | Latest | Vision AI |

---

## Setup on Windows

### Step 1 — Install Python

Download from https://www.python.org/downloads/ (choose 3.12.x)

During install, **check "Add python.exe to PATH"** before clicking Install.

Verify:
```cmd
python --version
```
Expected: `Python 3.12.x`

---

### Step 2 — Install Node.js

Download the LTS installer from https://nodejs.org/

Run the installer with all defaults.

Verify:
```cmd
node --version
npm --version
```
Expected: `v20.x.x` and `10.x.x`

---

### Step 3 — Install Ollama

Download from https://ollama.com/download and run the installer.

After install, Ollama runs as a background service automatically on Windows.

Verify:
```cmd
ollama --version
```

Pull the required models (this downloads ~9 GB total — do this on a good connection):
```cmd
ollama pull llava:latest
ollama pull qwen2.5:7b
```

Verify models downloaded:
```cmd
ollama list
```
You should see both `llava:latest` and `qwen2.5:7b` listed.

---

### Step 5 — Backend Setup

Open **Command Prompt** or **PowerShell** in the project root.

Create a virtual environment:
```cmd
python -m venv .venv
```

Activate it:
```cmd
.venv\Scripts\activate
```

Your prompt should now show `(.venv)` at the start.

Install Python packages:
```cmd
pip install --upgrade pip
pip install -r backend\requirements.txt
```

Install Playwright's Chromium browser:
```cmd
playwright install chromium
```

---

### Step 6 — Frontend Setup

Open a **second** Command Prompt in the project root.

```cmd
cd frontend
npm install
```

Verify the build works:
```cmd
npm run build
```
Expected output ends with `✓ built in Xs`

---

### Step 7 — Environment Configuration (Optional)

All defaults work out of the box. Only create this file if you need to change something.

Create `backend\.env`:
```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_VISION_MODEL=llava:latest
OLLAMA_TEXT_MODEL=qwen2.5:7b
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_TIMEOUT=60000
DEBUG=false
```

---

### Step 8 — Seed Sample Banners

From the project root with the virtual environment active:
```cmd
python scripts\seed.py
```

Expected:
```
  added: Bayer CS · Nubeqa Safety 300x250
  added: Gilead · LMS Link Content Overlapping Demo
  ...
Seed complete.
```

---

## Running the Application

You need **three** Command Prompt windows open at the same time.

### Window 1 — Ollama (already running as a service on Windows)

Just verify it is running:
```cmd
curl http://localhost:11434/api/tags
```
If it returns JSON, Ollama is ready. If not, open the Ollama app from the Start menu.

### Window 2 — Backend

```cmd
cd bannermind_v10_vision_updated
.venv\Scripts\activate
cd backend
uvicorn backend.main:app --port 8000 --loop asyncio 
```

Expected:
```
INFO:     Uvicorn running on http://127.0.0.1:8000/
INFO:     Application startup complete.
```

### Window 3 — Frontend

```cmd
cd frontend
npm run dev
```

Expected:
```
  VITE v5.x.x  ready

  ➜  Local:   http://localhost:5173/
```

Open **http://localhost:5173** in your browser.

---

## Running a Test

1. Go to **Banners** in the navigation
2. Click **Run Tests** on any banner
3. You are taken to the run page — the live log streams in real time
4. After ~10-15 minutes all 7 checks complete
5. Failed checks auto-expand with screenshot evidence and AI reasoning

---

## Troubleshooting

**`python` not found after install**
Close and reopen Command Prompt, or run:
```cmd
py --version
```
Use `py` instead of `python` throughout if needed.

**`playwright install chromium` fails**
Run Command Prompt as Administrator, then retry.

**Ollama not responding on port 11434**
Open the Ollama app from the Start menu, or run:
```cmd
ollama serve
```

**Backend fails with "Address in use" on port 8000**
```cmd
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**Frontend shows "Network Error"**
The backend is not running. Start it in Window 2 first.

**Tests take a very long time**
Vision analysis on CPU takes 60-120 seconds per check. Total run time of 10-15 minutes is normal. A GPU (NVIDIA with CUDA) speeds this up significantly — Ollama detects it automatically.

**`npm install` fails with EACCES or permission errors**
Run Command Prompt as Administrator for the npm install step only.

---

## Dependencies Reference

### Python — `backend/requirements.txt`

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
aiosqlite==0.20.0
playwright==1.44.0
httpx==0.27.0
pydantic==2.7.1
pydantic-settings==2.2.1
python-dotenv==1.0.1
loguru==0.7.2
```

### Node.js — `frontend/package.json`

```json
"dependencies": {
  "react": "^18.3.1",
  "react-dom": "^18.3.1",
  "react-router-dom": "^6.23.1",
  "@tanstack/react-query": "^5.40.0",
  "axios": "^1.7.2",
  "clsx": "^2.1.1",
  "date-fns": "^3.6.0",
  "lucide-react": "^0.383.0"
},
"devDependencies": {
  "@types/react": "^18.3.3",
  "@types/react-dom": "^18.3.0",
  "@vitejs/plugin-react": "^4.3.0",
  "autoprefixer": "^10.4.19",
  "postcss": "^8.4.38",
  "tailwindcss": "^3.4.4",
  "typescript": "^5.4.5",
  "vite": "^5.2.13"
}
```

### Ollama Models

| Model | Size | Purpose |
|-------|------|---------|
| `llava:latest` | ~4.7 GB | Reads screenshots — vision analysis |
| `qwen2.5:7b` | ~4.7 GB | Planning text generation |

---

## Quick Command Reference

```cmd
:: One-time setup
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
playwright install chromium
cd frontend && npm install && cd ..
python scripts\seed.py


:: Every time — Window 2 (backend)
.venv\Scripts\activate
cd backend
uvicorn backend.main:app --port 8000 --loop asyncio 

:: Every time — Window 3 (frontend)
cd frontend
npm run dev

:: Open browser
start http://localhost:5173
```