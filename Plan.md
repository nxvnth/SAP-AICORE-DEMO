# SAP AI Core Demo — Step-by-Step Implementation Plan

A handoff-ready plan covering every component in the architecture diagram. Each phase ends with a checkpoint so anyone can pick up from that point.

**6 phases · ~1–2 days total · Azure VM (pre-provisioned) + all other services free · Python · LangChain · ChromaDB · RAG Chatbot · SAP AI Core**

---

## Phase 1 — SAP BTP Account & AI Core Instance
*Infrastructure · ~45 min*

### 1.1 Create SAP BTP Trial Account

Go to https://www.sap.com/products/technology-platform/trial.html and sign up for the free trial.

- Use a personal or work email (avoid disposable addresses — SAP verifies them).
- When prompted for a region, choose **US East (VA)** or **EU West (Netherlands)** — both have AI Core available.
- After email verification, your global account is provisioned automatically. This takes 2–5 minutes.

### 1.2 Create a Subaccount

In the BTP Cockpit (https://cockpit.hanatrial.ondemand.com):

- Click **Go To Your Trial Account**.
- A default subaccount named `trial` is already created. Use it — no need to create a new one.
- Note the **Subaccount ID** and **Region** from the subaccount overview. Save these.

### 1.3 Provision SAP AI Core Service Instance

Inside the trial subaccount:

- Navigate to **Services → Service Marketplace** and search for "AI Core".
- Click **Create**. Plan: `extended` (this is the free trial plan that includes GenAI Hub access).
- Instance name: `ai-core-demo`. Leave other settings as default.
- Creation takes 3–10 minutes. The status will show **Created** when done.

> ⚠️ If you only see a "free" plan (not "extended"), your BTP trial region doesn't support GenAI Hub. Switch region to US East or EU West before provisioning.

### 1.4 Create a Service Key (API credentials)

These credentials are how your app authenticates with AI Core.

- In the AI Core instance page → **Service Keys → Create**.
- Name it `ai-core-key`.
- After creation, click the key and **download the JSON**. Save it as `ai_core_credentials.json`. **Keep this file private — never commit it to Git.**

The JSON will contain these fields — note them down:

```json
{
  "clientid":      "sb-...",
  "clientsecret":  "...",
  "url":           "https://...authentication.sap.hana.ondemand.com",
  "serviceurls": {
    "AI_API_URL": "https://api.ai.internalprod.eu-central-1.aws.ml.hana.ondemand.com"
  }
}
```

### 1.5 Enable GenAI Hub & Verify Model Access

- Navigate to your subaccount → **Instances and Subscriptions**.
- Find your AI Core instance → open the **SAP AI Launchpad** (subscribe to it from the Service Marketplace — it's free).
- In AI Launchpad → **GenAI Hub → Models**. You should see GPT-4o, Claude, and Gemini listed.
- If models aren't visible yet, wait 10 minutes and refresh. The entitlement sync takes time on trial accounts.

### ✅ Checkpoint 1 — Save before handing off

You have: (1) a BTP Trial account you can log into, (2) a provisioned AI Core instance in "Created" state, (3) a downloaded `ai_core_credentials.json` stored somewhere safe, (4) confirmed GenAI Hub models visible in AI Launchpad. The next person needs the credentials file and BTP login.

---

## Phase 2 — GitHub Repository & Workflow Templates
*Templates · ~30 min*

### 2.1 Create the GitHub Repository

AI Core polls a Git repository for workflow and serving templates. This is the source of truth for your AI pipeline definitions.

- Create a new **public** GitHub repo named `sap-aicore-demo`.
- Initialize with a README.
- Create the following folder structure:

```
sap-aicore-demo/
├── workflows/
│   └── ingest-workflow.yaml   # batch workflow: loads docs from MinIO → ChromaDB
├── serving/
│   └── rag-serving.yaml       # serving template: runs the RAG chatbot endpoint
├── app/
│   ├── main.py                # FastAPI chatbot + RAG logic (Phase 6)
│   ├── ingest.py              # document ingestion script (Phase 6)
│   ├── auth.py                # AI Core OAuth token helper (Phase 6)
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .dockerignore          # prevents secrets leaking into the image
│   └── docs/                  # sample documents for RAG (PDFs, txts)
│       └── sample.pdf
├── .gitignore                 # prevents secrets being committed
└── README.md
```

Create `.gitignore` at the repo root immediately after creating the repo — before any other files are added:

```gitignore
# Secrets — never commit these
.env
*.json
ai_core_credentials.json

# Python
__pycache__/
*.pyc
.venv/

# ChromaDB local data
chroma_db/

# OS
.DS_Store
```

### 2.2 Write the Serving Template (rag-serving.yaml)

This tells AI Core how to run your RAG chatbot as a live inference endpoint. All secrets are injected via Kubernetes `secretKeyRef` — nothing is hardcoded.

```yaml
# serving/rag-serving.yaml
apiVersion: ai.sap.com/v1alpha1
kind: ServingTemplate
metadata:
  name: rag-serving-template
  labels:
    scenarios.ai.sap.com/id: "rag-chatbot-scenario"
    ai.sap.com/version: "1.0.0"
spec:
  template:
    apiVersion: serving.kserve.io/v1beta1
    metadata:
      annotations:
        autoscaling.knative.dev/metric: concurrency
        autoscaling.knative.dev/target: "1"
        autoscaling.knative.dev/targetUtilizationPercentage: "100"
    spec:
      predictor:
        imagePullSecrets:
          - name: docker-registry-secret
        containers:
          - name: kserve-container
            image: "docker.io/COMPANY_DOCKERHUB_USERNAME/sap-aicore-demo:latest"
            ports:
              - containerPort: 8080
                protocol: TCP
            env:
              - name: AICORE_AUTH_URL
                valueFrom:
                  secretKeyRef:
                    name: aicore-secret
                    key: AICORE_AUTH_URL
              - name: AICORE_CLIENT_ID
                valueFrom:
                  secretKeyRef:
                    name: aicore-secret
                    key: AICORE_CLIENT_ID
              - name: AICORE_CLIENT_SECRET
                valueFrom:
                  secretKeyRef:
                    name: aicore-secret
                    key: AICORE_CLIENT_SECRET
              - name: MINIO_ENDPOINT
                valueFrom:
                  secretKeyRef:
                    name: aicore-secret
                    key: MINIO_ENDPOINT
              - name: MINIO_ACCESS_KEY
                valueFrom:
                  secretKeyRef:
                    name: aicore-secret
                    key: MINIO_ACCESS_KEY
              - name: MINIO_SECRET_KEY
                valueFrom:
                  secretKeyRef:
                    name: aicore-secret
                    key: MINIO_SECRET_KEY
```

> ⚠️ Replace `COMPANY_DOCKERHUB_USERNAME` with the company Docker Hub username your manager provides. The secret values are never written into this file — they are injected at runtime from `aicore-secret`, which you register in Phase 5.

### 2.3 Write the Workflow Template (ingest-workflow.yaml)

This defines the batch ingestion job — it runs `ingest.py` which pulls documents from MinIO, splits them into chunks, embeds them, and stores the vectors in ChromaDB on the VM. You run this once before the chatbot goes live, and again whenever documents are updated.

```yaml
# workflows/ingest-workflow.yaml
apiVersion: argoproj.io/v1alpha1
kind: WorkflowTemplate
metadata:
  name: rag-ingest-workflow
  labels:
    scenarios.ai.sap.com/id: "rag-chatbot-scenario"
    ai.sap.com/version: "1.0.0"
spec:
  templates:
    - name: ingest-docs
      container:
        image: "docker.io/COMPANY_DOCKERHUB_USERNAME/sap-aicore-demo:latest"
        command: ["python", "ingest.py"]
        env:
          - name: MINIO_ENDPOINT
            valueFrom:
              secretKeyRef:
                name: aicore-secret
                key: MINIO_ENDPOINT
          - name: MINIO_ACCESS_KEY
            valueFrom:
              secretKeyRef:
                name: aicore-secret
                key: MINIO_ACCESS_KEY
          - name: MINIO_SECRET_KEY
            valueFrom:
              secretKeyRef:
                name: aicore-secret
                key: MINIO_SECRET_KEY
          - name: AICORE_AUTH_URL
            valueFrom:
              secretKeyRef:
                name: aicore-secret
                key: AICORE_AUTH_URL
          - name: AICORE_CLIENT_ID
            valueFrom:
              secretKeyRef:
                name: aicore-secret
                key: AICORE_CLIENT_ID
          - name: AICORE_CLIENT_SECRET
            valueFrom:
              secretKeyRef:
                name: aicore-secret
                key: AICORE_CLIENT_SECRET
  entrypoint: ingest-docs
```

### 2.4 Generate a GitHub Personal Access Token

AI Core needs to read your repo. Generate a token so you can register the repo in Phase 5.

- GitHub → Settings → Developer Settings → Personal Access Tokens → **Tokens (classic)**.
- Scopes needed: `repo` (read access is enough).
- Name it `sap-aicore-demo-pat` and save the token value — it's shown only once.

### ✅ Checkpoint 2 — Save before handing off

You have: (1) a GitHub repo with the folder structure and both YAML templates committed, (2) your GitHub PAT saved securely. The next person needs the repo URL, PAT, and the BTP credentials from Phase 1.

---

## Phase 3 — Docker Image: Placeholder First, Real Build Later
*Containerisation · ~45 min*

The app code doesn't exist yet — it gets written in Phase 6. But the YAML templates in Phase 2 need a valid image reference right now. The solution is a two-pass approach: push a placeholder image first so the pipeline can be wired up, then replace it with the real image once the code is written.

All images are pushed to the **company Docker Hub account** (credentials provided by your manager). Your personal account is used only for local testing — never for pushing.

---

### 3.1 Confirm Company Docker Hub Credentials

Your manager will provide:
- Company Docker Hub username (referred to as `COMPANY_DOCKERHUB_USERNAME` throughout this plan)
- An access token (not the account password — tokens are scoped and revocable)

Store these in your local password manager. Do not save them in any file inside the repo.

Log in on your laptop and on the VM:

```bash
# On your laptop
docker login -u COMPANY_DOCKERHUB_USERNAME
# Enter the access token when prompted — not the account password

# Also do this on the VM (SSH in first)
ssh azureuser@YOUR_VM_PUBLIC_IP
docker login -u COMPANY_DOCKERHUB_USERNAME
```

---

### 3.2 Write the .dockerignore File

Create `app/.dockerignore` before writing the Dockerfile. This ensures secrets and local files never get copied into the image even accidentally:

```dockerignore
# Secrets — must never end up in the image
.env
*.json
ai_core_credentials.json

# Local Python environment
.venv/
__pycache__/
*.pyc
*.pyo

# Local vector DB data (rebuilt inside the container from MinIO)
chroma_db/

# Dev/editor files
.DS_Store
*.md
.git/
```

---

### 3.3 Write the Dockerfile

This single Dockerfile serves both the chatbot (`main.py`) and the ingestion job (`ingest.py`). Which one runs is controlled by the `CMD` passed at runtime in the YAML templates.

```dockerfile
# app/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching — only rebuilds if requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code — .dockerignore ensures .env is never copied
COPY main.py .
COPY ingest.py .
COPY auth.py .

# The app listens on 8080 (required by KServe / SAP AI Core)
EXPOSE 8080

# Default: run the chatbot server
# Override with ["python", "ingest.py"] in the workflow template
CMD ["python", "main.py", "--mode", "serve"]
```

---

### 3.4 Write requirements.txt

```
# app/requirements.txt
langchain==0.2.16
langchain-openai==0.1.23          # AI Core uses OpenAI-compatible endpoints
langchain-community==0.2.16       # document loaders (PDF, text)
fastapi==0.111.0
uvicorn==0.30.6
boto3==1.34.0                      # MinIO on Azure VM (S3-compatible)
chromadb==0.5.3                    # local vector store for RAG
sentence-transformers==3.0.1       # local embedding model (no extra API needed)
pypdf==4.3.1                       # PDF document loader
python-dotenv==1.0.1
httpx==0.27.0
requests==2.32.3
```

---

### 3.5 Pass 1 — Push a Placeholder Image

Before the app code is written, push a minimal placeholder just to give the YAML templates a valid image to reference. This unblocks Phases 4 and 5.

```bash
# On your laptop — tag the official python image as your placeholder
docker pull python:3.11-slim
docker tag python:3.11-slim COMPANY_DOCKERHUB_USERNAME/sap-aicore-demo:latest
docker push COMPANY_DOCKERHUB_USERNAME/sap-aicore-demo:latest
```

The placeholder image does nothing useful — it's just a valid pullable reference. AI Core will pull it successfully but the container will exit immediately. That's fine at this stage.

> ⚠️ This is the only time you push from your laptop. All subsequent real builds go through the VM or GitHub Actions (see 3.6).

---

### 3.6 Pass 2 — Build and Push the Real Image (3 options)

Once the app code is written in Phase 6, rebuild and push the real image. Choose one of the three approaches below.

---

**Option A — Build on the VM (simplest, recommended to start)**

Every time you change code: push to GitHub from your laptop, SSH into the VM, pull and rebuild.

```bash
# On your laptop — push code changes to GitHub as normal
git add .
git commit -m "update RAG chatbot"
git push origin main

# Then SSH into the VM
ssh azureuser@YOUR_VM_PUBLIC_IP

# Pull latest code and rebuild
cd ~
git clone https://github.com/YOUR_PERSONAL_GITHUB/sap-aicore-demo  # first time only
cd sap-aicore-demo
git pull origin main

# Build and push using the company Docker Hub account
# (you already ran docker login in step 3.1)
cd app
docker build -t COMPANY_DOCKERHUB_USERNAME/sap-aicore-demo:latest .
docker push COMPANY_DOCKERHUB_USERNAME/sap-aicore-demo:latest
```

After pushing, restart the AI Core deployment to pick up the new image:
AI Launchpad → Deployments → your deployment → **Restart**.

---

**Option B — GitHub Actions (automated, triggers on every push)**

Add a workflow file to your personal GitHub repo. On every push to `main`, GitHub builds the image and pushes it to the company Docker Hub account automatically — no SSH required.

First, add the company Docker Hub credentials as GitHub Actions secrets (they are never visible in code):
- Your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**.
- Add `DOCKERHUB_USERNAME` = `COMPANY_DOCKERHUB_USERNAME`
- Add `DOCKERHUB_TOKEN` = the company Docker Hub access token

Then create `.github/workflows/docker-build.yml` in your repo:

```yaml
# .github/workflows/docker-build.yml
name: Build and Push Docker Image

on:
  push:
    branches: [main]
    paths:
      - 'app/**'           # only triggers when app code changes

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Log in to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: ./app
          platforms: linux/amd64
          push: true
          tags: ${{ secrets.DOCKERHUB_USERNAME }}/sap-aicore-demo:latest
```

After this is in place: push code → image updates automatically → restart AI Core deployment to pick it up.

> ℹ️ The company Docker Hub credentials exist only in GitHub's encrypted secrets store. They never appear in your code, your `.env`, or the repo history.

---

**Option C — Docker Hub Automated Builds (triggers on every push, no VM or Actions needed)**

Docker Hub has a native automated build feature that links directly to a GitHub repository. Every push to `main` triggers a build on Docker Hub's own infrastructure and pushes the resulting image automatically — no VM SSH and no GitHub Actions configuration required.

> ⚠️ This feature requires a **paid Docker Hub plan** (Pro or above). The exact current price should be confirmed at https://hub.docker.com/billing/plan before committing — your manager will need to approve this. The Azure VM credits are already approved, so this is an additional line item to check.

Once the paid plan is active on the company Docker Hub account:

- Log into Docker Hub with the company account → go to the `sap-aicore-demo` repository → **Builds → Configure Automated Builds**.
- Link it to your personal GitHub account and select the `sap-aicore-demo` repo.
- Set the build rule: Branch `main`, Dockerfile location `/app/Dockerfile`, tag `latest`.
- Save. From this point on, every push to `main` automatically builds and pushes the image.

The flow becomes: push code from laptop → Docker Hub detects the push → builds and publishes the image → restart the AI Core deployment to pick it up.

> ℹ️ The GitHub repo can be your personal account — Docker Hub only needs read access to pull the code. The resulting image is published under the company Docker Hub account. Your personal account credentials are never stored anywhere in the project.

---

### ✅ Checkpoint 3 — Save before handing off

You have: a placeholder image at `COMPANY_DOCKERHUB_USERNAME/sap-aicore-demo:latest` that can be pulled, `.dockerignore` committed, `Dockerfile` and `requirements.txt` committed, and your chosen build approach (A, B, or C) documented. The next person needs: company Docker Hub credentials (from your manager), and if using Option B, the GitHub Actions secrets already configured.

---

## Phase 4 — MinIO Object Store on Azure VM
*Object Store · ~45 min*

MinIO is an open-source, S3-compatible object store that runs as a single binary. SAP AI Core will talk to it exactly the same way it would talk to AWS S3 or Cloudflare R2 — nothing else in the plan changes.

### 4.1 SSH Into the VM

Get the VM's public IP from the Azure Portal → your VM → **Overview**.

```bash
ssh azureuser@YOUR_VM_PUBLIC_IP
# If your manager set up an SSH key, add: -i ~/.ssh/your_key.pem
```

### 4.2 Open Port 9000 in Azure Network Security Group

MinIO listens on port 9000 (API) and 9001 (web console). You need to allow inbound traffic on both.

In the Azure Portal:
- Go to your VM → **Networking → Add inbound port rule**.
- Add rule 1: Destination port `9000`, Protocol `TCP`, Name `minio-api`.
- Add rule 2: Destination port `9001`, Protocol `TCP`, Name `minio-console`.

> ⚠️ For a demo this is fine, but in production you'd restrict source IPs. For now, setting Source to `Any` is acceptable.

### 4.3 Install MinIO and Docker on the VM

SSH'd into the VM, run:

```bash
# --- Install Docker (needed for Option A builds in Phase 3) ---
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io
sudo usermod -aG docker azureuser   # lets azureuser run docker without sudo
newgrp docker                        # apply group change without logging out

# --- Install MinIO ---
wget https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x minio
sudo mv minio /usr/local/bin/

# Create a directory for stored data
sudo mkdir -p /data/minio
sudo chown azureuser:azureuser /data/minio

# Verify both
docker --version
minio --version
```

### 4.4 Create a systemd Service (so MinIO survives reboots)

```bash
sudo nano /etc/systemd/system/minio.service
```

Paste the following — replace the credentials with your own strong values:

```ini
[Unit]
Description=MinIO Object Storage
After=network.target

[Service]
User=azureuser
Group=azureuser
Environment="MINIO_ROOT_USER=minioadmin"
Environment="MINIO_ROOT_PASSWORD=CHANGE_THIS_STRONG_PASSWORD"
ExecStart=/usr/local/bin/minio server /data/minio --console-address ":9001"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable minio
sudo systemctl start minio

# Confirm it's running
sudo systemctl status minio
```

### 4.5 Create the Demo Bucket

Use the MinIO CLI (`mc`) to create a bucket — this is equivalent to creating an R2 or S3 bucket.

```bash
# Install mc (MinIO client)
wget https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc
sudo mv mc /usr/local/bin/

# Point mc at your local MinIO instance
mc alias set local http://localhost:9000 minioadmin CHANGE_THIS_STRONG_PASSWORD

# Create the bucket
mc mb local/sap-aicore-demo-store

# Verify
mc ls local
```

You can also access the MinIO web console at `http://YOUR_VM_PUBLIC_IP:9001` in a browser to confirm the bucket exists.

### 4.6 Create a Dedicated Access Key for the App

Rather than using the root credentials in your app, create a scoped key:

```bash
# Create a new user
mc admin user add local demouser DEMO_USER_SECRET_PASSWORD

# Attach read/write policy
mc admin policy attach local readwrite --user demouser
```

Use `demouser` / `DEMO_USER_SECRET_PASSWORD` as the access credentials everywhere else in the plan (the `.env` file in Phase 6, and the AI Core object store registration below).

### 4.7 Register the Object Store in SAP AI Core

Via AI Launchpad: **Administration → Object Stores → Add**. Fill in:

```
Type:        S3-compatible
Endpoint:    http://YOUR_VM_PUBLIC_IP:9000
Bucket:      sap-aicore-demo-store
Region:      us-east-1        # MinIO accepts any non-empty string here
Access Key:  demouser
Secret Key:  DEMO_USER_SECRET_PASSWORD
Path Prefix: demo/            # optional, keeps things organised
```

> ⚠️ Note `http://` not `https://` — MinIO is running without TLS in this setup. For a production deployment you'd put it behind nginx with a certificate, but for a demo this is fine.

### ✅ Checkpoint 4 — Save before handing off

You have: Docker and MinIO running on the Azure VM, MinIO as a systemd service (confirm with `systemctl status minio`), a bucket named `sap-aicore-demo-store`, a scoped access key created, the web console accessible at `http://YOUR_VM_PUBLIC_IP:9001`, and the object store registered in AI Core. The next person needs: VM public IP, MinIO access key (`demouser`), and the secret password.

---

## Phase 4b — ChromaDB on the Azure VM
*Vector Store · ~15 min*

ChromaDB is the vector database that makes RAG work. It stores the embedded representations of your documents so the chatbot can retrieve relevant chunks at query time. It runs as a persistent server on the same VM as MinIO — the 8 GB RAM is more than enough for both.

### 4b.1 Open Port 8000 in Azure NSG

- Azure Portal → your VM → **Networking → Add inbound port rule**.
- Destination port: `8000`, Protocol: `TCP`, Name: `chromadb`.

### 4b.2 Install and Run ChromaDB as a systemd Service

SSH into the VM:

```bash
# Install ChromaDB
pip3 install chromadb

# Create data directory
sudo mkdir -p /data/chroma
sudo chown azureuser:azureuser /data/chroma
```

Create the systemd service:

```bash
sudo nano /etc/systemd/system/chromadb.service
```

```ini
[Unit]
Description=ChromaDB Vector Store
After=network.target

[Service]
User=azureuser
Group=azureuser
ExecStart=chroma run --path /data/chroma --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable chromadb
sudo systemctl start chromadb

# Confirm it's running
sudo systemctl status chromadb

# Quick health check
curl http://localhost:8000/api/v1/heartbeat
# Expected: {"nanosecond heartbeat": ...}
```

### 4b.3 Add ChromaDB to the .env and YAML Secrets

Add to `app/.env` (local development):

```env
CHROMA_HOST=YOUR_VM_PUBLIC_IP
CHROMA_PORT=8000
```

This same value will be injected as a secret in the serving/workflow templates — add it to `aicore-secret` in Phase 5 alongside the other credentials.

---

## Phase 5 — Register Resources & Create a Deployment in AI Core
*AI Core Wiring · ~45 min*

> ℹ️ All of Phase 5 can be done through the **SAP AI Launchpad UI** — no API calls required for a demo.

### 5.1 Register Your GitHub Repository

AI Core needs to sync your workflow/serving YAMLs from GitHub.

- AI Launchpad → **ML Operations → Git Repositories → Add**.
- URL: `https://github.com/YOUR_USERNAME/sap-aicore-demo`
- Username: your GitHub username.
- Password/Token: the PAT from Phase 2.4.
- After saving, AI Core will scan the repo and discover your YAML files (~2 minutes).
- Confirm: in **ML Operations → Applications**, the templates should appear.

### 5.2 Create a Scenario

A Scenario groups all your templates and deployments. It must match the `scenarios.ai.sap.com/id` label in your YAML files.

- AI Launchpad → **ML Operations → Scenarios → Create**.
- ID: `rag-chatbot-scenario` (must exactly match the label in your YAMLs).
- Name: `RAG Chatbot Scenario`.

### 5.3 Create a Resource Group

Resource groups provide namespace isolation. For a demo, use the `default` resource group which already exists.

- AI Launchpad → **Administration → Resource Groups** — confirm `default` is listed.
- If not, create one with ID `default`.

### 5.4 Register Docker Hub Secret

AI Core needs credentials to pull the company Docker image.

- AI Launchpad → **Administration → Docker Registry Secrets → Add**.
- Name: `docker-registry-secret` (must match the name in your serving YAML).
- Server: `https://index.docker.io/v1/`
- Username: `COMPANY_DOCKERHUB_USERNAME`
- Password: the company Docker Hub access token (from your manager — use the token, not the account password).

### 5.5 Register the App Secrets (aicore-secret)

All the environment variables your app needs at runtime — AI Core credentials, MinIO credentials, ChromaDB host — are stored as a single Kubernetes secret called `aicore-secret`. This is what the `secretKeyRef` entries in the YAML templates pull from.

Via AI Launchpad → **Administration → Secrets → Create**. Name: `aicore-secret`. Add the following key-value pairs one by one:

```
AICORE_AUTH_URL        = https://YOUR_AUTH_DOMAIN.authentication.sap.hana.ondemand.com
AICORE_CLIENT_ID       = sb-...
AICORE_CLIENT_SECRET   = ...
AICORE_API_URL         = https://api.ai.internalprod.eu-central-1.aws.ml.hana.ondemand.com
MINIO_ENDPOINT         = http://YOUR_VM_PUBLIC_IP:9000
MINIO_ACCESS_KEY       = demouser
MINIO_SECRET_KEY       = DEMO_USER_SECRET_PASSWORD
MINIO_BUCKET           = sap-aicore-demo-store
CHROMA_HOST            = YOUR_VM_PUBLIC_IP
CHROMA_PORT            = 8000
```

> ℹ️ These values come from `ai_core_credentials.json` (Phase 1.4) and the MinIO/ChromaDB setup in Phase 4. Once registered here, they never need to be in any file — the container reads them from the environment at runtime.

### 5.6 Create a Configuration

A Configuration binds your serving template to runtime parameters.

- AI Launchpad → **ML Operations → Configurations → Create**.
- Scenario: `rag-chatbot-scenario`.
- Template: select `rag-serving-template` (from your YAML).
- Name: `rag-chatbot-config`.

### 5.7 Create & Start a Deployment

This actually spins up your container on AI Core's Kubernetes cluster.

- AI Launchpad → **ML Operations → Deployments → Create**.
- Select configuration: `rag-chatbot-config`.
- Duration: **Standard** (stays running until you stop it).
- Click **Review → Deploy**.
- Status will move: `UNKNOWN → PENDING → RUNNING`. This takes 5–15 minutes.
- Once `RUNNING`, copy the **Deployment URL** and **Deployment ID** — save both.

> ⚠️ Trial accounts may have a quota of 1–2 concurrent deployments. If you hit a quota error, check AI Launchpad → Administration → Resource Groups for quota details.

### 5.8 Test the Deployment (Health Check)

```bash
# Get an OAuth token using your service key credentials
TOKEN=$(curl -s -X POST \
  "YOUR_AUTH_URL/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Hit the deployment health endpoint
curl -H "Authorization: Bearer $TOKEN" \
     "YOUR_DEPLOYMENT_URL/v1/health"

# Expected response: {"status": "OK"}
```

### ✅ Checkpoint 5 — Save before handing off

You have: a running deployment in AI Core with status RUNNING, and a Deployment URL that responds to health checks. Save the Deployment URL and Deployment ID alongside the credentials JSON. The next person only needs Phase 6 to complete the demo.

---

## Phase 6 — RAG Chatbot App (Python / LangChain)
*Application · ~2 hrs*

The app has three files: `auth.py` (token management with caching), `ingest.py` (loads documents from MinIO → ChromaDB), and `main.py` (the FastAPI chatbot that retrieves context and calls the LLM).

---

### 6.1 Set Up Local Environment

```bash
# Clone your repo
git clone https://github.com/YOUR_PERSONAL_GITHUB/sap-aicore-demo
cd sap-aicore-demo/app

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Create `app/.env` for local development (never commit this — it's in `.gitignore`):

```env
# AI Core — copy values from ai_core_credentials.json
AICORE_AUTH_URL=https://YOUR_AUTH_DOMAIN.authentication.sap.hana.ondemand.com
AICORE_CLIENT_ID=sb-...
AICORE_CLIENT_SECRET=...
AICORE_API_URL=https://api.ai.internalprod.eu-central-1.aws.ml.hana.ondemand.com
AICORE_RESOURCE_GROUP=default
AICORE_DEPLOYMENT_ID=YOUR_DEPLOYMENT_ID

# MinIO on Azure VM
MINIO_ENDPOINT=http://YOUR_VM_PUBLIC_IP:9000
MINIO_ACCESS_KEY=demouser
MINIO_SECRET_KEY=DEMO_USER_SECRET_PASSWORD
MINIO_BUCKET=sap-aicore-demo-store

# ChromaDB on Azure VM
CHROMA_HOST=YOUR_VM_PUBLIC_IP
CHROMA_PORT=8000
```

> ℹ️ `AICORE_DEPLOYMENT_ID` can't be filled in until Phase 5.7 is complete. Leave it blank for now. Inside AI Core the container reads all these values from `aicore-secret` — the `.env` is only for local development.

---

### 6.2 Write auth.py — Token Management with Caching

The OAuth token from AI Core expires after ~12 hours. This helper caches it and only refreshes when it's near expiry — avoids a redundant HTTP call on every chat message.

```python
# app/auth.py
import os, time, requests
from dotenv import load_dotenv

load_dotenv()

_token_cache = {"token": None, "expires_at": 0}

def get_token() -> str:
    """Return a valid AI Core OAuth token, refreshing only if near expiry."""
    now = time.time()
    # Refresh if expired or within 5 minutes of expiry
    if _token_cache["token"] is None or now >= _token_cache["expires_at"] - 300:
        resp = requests.post(
            f"{os.environ['AICORE_AUTH_URL']}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": os.environ["AICORE_CLIENT_ID"],
                "client_secret": os.environ["AICORE_CLIENT_SECRET"],
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = now + data.get("expires_in", 43200)
    return _token_cache["token"]
```

---

### 6.3 Write ingest.py — Load Documents into ChromaDB

This script runs once (and again whenever documents change). It pulls files from MinIO, splits them into chunks, embeds them using a local sentence-transformer model (no extra API cost), and stores the vectors in ChromaDB on the VM.

```python
# app/ingest.py
import os, boto3, tempfile
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
import chromadb

load_dotenv()

def get_minio_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )

def download_docs_from_minio(local_dir: str) -> list:
    """Download all files from MinIO bucket docs/ prefix to a local temp dir."""
    s3 = get_minio_client()
    bucket = os.environ["MINIO_BUCKET"]
    response = s3.list_objects_v2(Bucket=bucket, Prefix="docs/")
    paths = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        local_path = os.path.join(local_dir, Path(key).name)
        s3.download_file(bucket, key, local_path)
        paths.append(local_path)
        print(f"Downloaded: {key}")
    return paths

def load_documents(file_paths: list):
    docs = []
    for path in file_paths:
        if path.endswith(".pdf"):
            docs.extend(PyPDFLoader(path).load())
        elif path.endswith(".txt"):
            docs.extend(TextLoader(path).load())
    return docs

def main():
    print("Starting ingestion...")
    with tempfile.TemporaryDirectory() as tmp:
        file_paths = download_docs_from_minio(tmp)
        if not file_paths:
            print("No documents found in MinIO docs/ prefix. Upload some files first.")
            return

        docs = load_documents(file_paths)
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = splitter.split_documents(docs)
        print(f"Split into {len(chunks)} chunks")

        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        client = chromadb.HttpClient(
            host=os.environ["CHROMA_HOST"],
            port=int(os.environ["CHROMA_PORT"]),
        )
        vectorstore = Chroma(
            client=client,
            collection_name="rag_docs",
            embedding_function=embeddings,
        )
        vectorstore.add_documents(chunks)
        print(f"Ingestion complete. {len(chunks)} chunks stored in ChromaDB.")

if __name__ == "__main__":
    main()
```

Before running `ingest.py`, upload at least one document to MinIO under the `docs/` prefix:

```bash
mc alias set local http://YOUR_VM_PUBLIC_IP:9000 demouser DEMO_USER_SECRET_PASSWORD
mc cp your_document.pdf local/sap-aicore-demo-store/docs/your_document.pdf
```

Then run the ingestion locally:

```bash
python ingest.py
# Expected: "Ingestion complete. N chunks stored in ChromaDB."
```

---

### 6.4 Write main.py — The RAG Chatbot

```python
# app/main.py
import os, argparse
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferWindowMemory
import chromadb
from auth import get_token

load_dotenv()

def make_llm():
    token = get_token()
    base_url = (
        f"{os.environ['AICORE_API_URL']}"
        f"/v2/inference/deployments/{os.environ['AICORE_DEPLOYMENT_ID']}"
    )
    return AzureChatOpenAI(
        openai_api_key=token,
        openai_api_base=base_url,
        openai_api_version="2024-02-01",
        deployment_name="gpt-4o",
        model_name="gpt-4o",
        temperature=0.3,
    )

def make_retriever():
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    client = chromadb.HttpClient(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ["CHROMA_PORT"]),
    )
    vectorstore = Chroma(
        client=client,
        collection_name="rag_docs",
        embedding_function=embeddings,
    )
    return vectorstore.as_retriever(search_kwargs={"k": 4})

# Initialise once at startup — not on every request
llm = make_llm()
retriever = make_retriever()
memory = ConversationBufferWindowMemory(
    memory_key="chat_history",
    return_messages=True,
    k=5,  # remember last 5 exchanges
)
chain = ConversationalRetrievalChain.from_llm(
    llm=llm,
    retriever=retriever,
    memory=memory,
    verbose=False,
)

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

@app.get("/v1/health")
def health():
    return {"status": "OK"}

@app.post("/v1/chat")
async def chat(req: ChatRequest):
    result = chain.invoke({"question": req.message})
    return {"response": result["answer"]}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["serve", "ingest"], default="serve")
    args = parser.parse_args()
    if args.mode == "ingest":
        import ingest
        ingest.main()
    else:
        uvicorn.run(app, host="0.0.0.0", port=8080)
```

---

### 6.5 Run Locally to Verify

```bash
# Step 1 — ingest documents first (ChromaDB must be running on the VM)
python ingest.py

# Step 2 — start the chatbot server
python main.py --mode serve

# Step 3 — test in another terminal
curl -X POST http://localhost:8080/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What does the document say about X?"}'

# Expected:
# {"response": "According to the document, X refers to..."}
```

---

### 6.6 Rebuild and Push the Real Docker Image

Now that the code is written, replace the placeholder image with the real one using whichever approach you chose in Phase 3.6.

**Option A (VM build):**
```bash
# Push code to GitHub from your laptop
git add . && git commit -m "RAG chatbot complete" && git push origin main

# SSH into VM, pull and rebuild
ssh azureuser@YOUR_VM_PUBLIC_IP
cd sap-aicore-demo && git pull origin main
cd app
docker build -t COMPANY_DOCKERHUB_USERNAME/sap-aicore-demo:latest .
docker push COMPANY_DOCKERHUB_USERNAME/sap-aicore-demo:latest
```

**Option B (GitHub Actions):** Just push to `main` — the workflow triggers automatically.

After pushing, restart the AI Core deployment:
AI Launchpad → Deployments → your deployment → **Restart**.

---

### 6.7 Run the Ingestion Workflow in AI Core

Before the chatbot can answer questions in production, ChromaDB needs to be populated via AI Core's workflow engine (not just locally). Trigger it:

- AI Launchpad → **ML Operations → Executions → Create**.
- Select the `rag-ingest-workflow` template.
- Click **Run**. Status moves to `COMPLETED` in a few minutes.
- Re-run this any time documents in MinIO change.

---

### 6.8 Optional — Gradio Chat UI for the Client Demo

Add a minimal browser-based chat interface so the client isn't staring at curl commands. Add `gradio==4.36.1` to `requirements.txt`, then create `app/ui.py`:

```python
# app/ui.py — run locally, points at the live AI Core deployment endpoint
import gradio as gr, requests, os
from dotenv import load_dotenv
load_dotenv()

ENDPOINT = os.environ.get("AICORE_DEPLOYMENT_URL", "http://localhost:8080")

def chat(message, history):
    resp = requests.post(f"{ENDPOINT}/v1/chat", json={"message": message})
    return resp.json()["response"]

gr.ChatInterface(fn=chat, title="SAP AI Core RAG Demo").launch()
```

Run with `python ui.py` — opens a chat UI in the browser at `http://localhost:7860`. Add `AICORE_DEPLOYMENT_URL` to your `.env` pointing at the live deployment URL from Phase 5.7.

---

### ✅ Checkpoint 6 — Demo Complete

You have: documents uploaded to MinIO, ChromaDB populated via the ingestion workflow, a running RAG chatbot deployment in AI Core that answers questions grounded in your documents, and optionally a Gradio UI for the live demo. Test end-to-end: ask a question about something specific in a document you uploaded — the answer should reference that content, not just general LLM knowledge.

---

## Handoff Cheat Sheet

**Files to keep safe — never commit any of these to Git**
- `ai_core_credentials.json` — AI Core OAuth credentials (Phase 1.4)
- `app/.env` — all runtime secrets for local development
- GitHub PAT — for AI Core to sync the repo (Phase 2.4)
- MinIO root password and `demouser` secret (Phase 4.4 / 4.6)
- Company Docker Hub access token (from manager)

**Credentials that live only in AI Core (never in files)**
- `aicore-secret` Kubernetes secret — registered in AI Launchpad Phase 5.5, contains all env vars the container needs at runtime

**URLs to record somewhere safe**
- BTP Cockpit: https://cockpit.hanatrial.ondemand.com
- AI Launchpad URL (from BTP Cockpit → Instances and Subscriptions)
- AI Core API base URL (`AI_API_URL` from credentials JSON)
- Deployment ID + Deployment URL (Phase 5.7)
- Azure VM public IP — MinIO API port 9000, console port 9001, ChromaDB port 8000

**Rebuild checklist (every time code changes)**
1. Push to GitHub from laptop
2. Build and push Docker image (Option A: SSH into VM and build / Option B: automatic via GitHub Actions)
3. Restart deployment in AI Launchpad
4. If documents changed: re-run ingestion workflow in AI Launchpad
