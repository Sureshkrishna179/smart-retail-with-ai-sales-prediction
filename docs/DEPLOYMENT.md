# SmartRetail AI — Cloud Deployment Guide

This guide details how to deploy **SmartRetail AI** with **100% free hosting** (zero credit card required) on modern cloud platforms, complete with automatic HTTPS, continuous deployment from GitHub, and optional free cloud MySQL.

---

## 🚀 Option 1: Render.com (Recommended — 100% Free Web Service)

Render provides a generous free tier for Python web services and Docker containers with automatic SSL certificates and continuous deployment from GitHub.

### Step 1: Push Repository to GitHub
Ensure your latest changes are pushed to your GitHub repository:
```bash
git push origin main
```

### Step 2: Create a Free Render Account
1. Visit [https://render.com](https://render.com) and sign in using your GitHub account.

### Step 3: Deploy via Blueprint (Fastest — 1 Click)
1. In the Render Dashboard, click **New +** ➔ **Blueprint**.
2. Connect your repository: `Sureshkrishna179/smart-retail-with-ai-sales-prediction`.
3. Render will automatically detect `render.yaml` and configure the service.
4. Click **Apply**.

--- OR Manual Setup in 2 Minutes ---

1. In the Render Dashboard, click **New +** ➔ **Web Service**.
2. Select your repository: `smart-retail-with-ai-sales-prediction`.
3. Configure the service settings:
   - **Name:** `smartretail-ai` (or any custom name)
   - **Region:** Closest to you (e.g., Singapore, Frankfurt, Oregon, Ohio)
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python -m smartretail.server`
   - **Instance Type:** `Free`
4. Add the following **Environment Variables** in the dashboard:
   | Key | Value | Purpose |
   |-----|-------|---------|
   | `PYTHONPATH` | `src` | Ensures Python modules resolve cleanly |
   | `REQUIRE_AUTH` | `0` (or `1` if you want login prompt) | Authentication toggle |
   | `JWT_SECRET` | *(Generate a 32-character random string)* | Secure token signing |
   | `ML_CACHE_SIGN_KEY` | *(Generate a 32-character random string)* | Forecast cache signing |
5. Click **Create Web Service**.
6. Render will build and deploy your app. Once deployed, open your public URL:
   `https://smartretail-ai-xxxx.onrender.com/dashboard.html`

> [!NOTE]
> Render free web services spin down after 15 minutes of inactivity. When a new visitor accesses the URL, it automatically wakes up within ~30–45 seconds.

---

## ⚡ Option 2: Koyeb (100% Free Micro Instance — No Sleep)

Koyeb offers a free Eco tier with 512MB RAM and continuous runtime (does not sleep).

1. Sign up at [https://www.koyeb.com](https://www.koyeb.com) via GitHub.
2. Click **Create App** ➔ Choose **GitHub**.
3. Select `smart-retail-with-ai-sales-prediction`.
4. Choose **Dockerfile** as the builder (Koyeb will auto-detect the root `Dockerfile`).
5. Set Port to `8765`.
6. Click **Deploy**.

---

## 🗄️ Free Cloud MySQL Database Setup (Optional)

The backend is built with an **in-memory architectural decoupling**:
- If MySQL is **offline or not connected**, the application still runs 100% of its ML prediction models, POS register, CSV intelligence engine, and dashboard telemetry seamlessly.
- If you want a **live persistent cloud database**, use one of these permanent free MySQL providers:

### Provider A: Aiven.io (Free 5GB Managed MySQL)
1. Sign up at [https://aiven.io](https://aiven.io) (Free Forever plan, no credit card required).
2. Create a new service: **MySQL** (select Free plan).
3. Copy the **Host**, **Port**, **User**, and **Password** from the overview page.
4. Set these in your Render/Koyeb environment variables:
   - `DB_HOST`: `<aiven-host>.aivencloud.com`
   - `DB_PORT`: `<aiven-port>`
   - `DB_USER`: `avnadmin`
   - `DB_PASSWORD`: `<your-aiven-password>`
   - `DB_NAME`: `defaultdb`

### Provider B: TiDB Cloud (Free 5GB Serverless MySQL-Compatible)
1. Sign up at [https://tidbcloud.com](https://tidbcloud.com).
2. Create a free **Serverless Cluster** (compatible with MySQL 8.0 protocol).
3. Connect and populate credentials into your cloud environment variables.

---

## 🌐 Option 3: Instant Public Demo in 30 Seconds (Tunneling)

If you are presenting in an interview or giving an immediate demo and want to expose your local running server to the internet without creating cloud accounts:

### Using Localtunnel (Zero Install with Node.js)
```bash
# 1. Start your local server
python -m smartretail.server

# 2. In another terminal, open a public HTTPS tunnel to port 8765
npx localtunnel --port 8765
```
Localtunnel will output a public URL (e.g. `https://bright-panda-82.loca.lt`). Anyone in the world can open that link and interact with your live application!

### Using Cloudflare Tunnels (Enterprise Grade, Free)
```bash
# Download cloudflared or run via winget
winget install --id Cloudflare.cloudflared

# Expose port 8765
cloudflared tunnel --url http://localhost:8765
```
Cloudflare immediately prints a high-speed, secure `https://<unique-id>.trycloudflare.com` URL.

---

## 🔒 Security Best Practices for Cloud Hosting

1. **Never commit `.env` files**: All sensitive secrets must be configured via the hosting provider's Environment Variables dashboard.
2. **CORS Whitelisting**: If connecting an external frontend or custom domain, set `CORS_ORIGINS` to your exact domain (`https://your-domain.com`).
3. **Health Check Endpoint**: The root container uses `/dashboard.html` for HTTP 200 health check validation.
