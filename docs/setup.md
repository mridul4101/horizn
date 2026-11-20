# Horizn Setup Guide

This guide walks you through setting up and running **Horizn** locally on macOS.

---

## 1. Prerequisites

Ensure your Mac meets the following requirements:

| Tool | Recommended | Purpose |
| :--- | :--- | :--- |
| **macOS** | 13+ (Ventura, Sonoma, Sequoia) | On-device Apple Vision Framework |
| **Python** | 3.11 | Backend API, ML clustering, image processing |
| **Node.js** | 18+ LTS | Vite + React frontend |
| **Homebrew** | Latest | Dependency package manager |
| **cloudflared** | Latest | Free ephemeral tunnel for Instagram image upload (`brew install cloudflared`) |

---

## 2. One-Time Installation

Clone the repository and run the automated setup script:

```bash
# Clone the repository
git clone https://github.com/your-username/horizn.git
cd horizn

# Run the automated setup script
./scripts/setup.sh
```

What `setup.sh` does:
1. Creates a Python virtual environment in `.venv/` using Python 3.11.
2. Installs required Python packages (`FastAPI`, `osxphotos`, `Pillow`, `pillow-heif`, `scikit-learn`, `imagehash`, `google-genai`, `pyobjc-framework-Vision`).
3. Installs frontend dependencies in `ui/` (`npm install`).
4. Creates necessary runtime directories (`data/exports/`).
5. Generates `.env` from `.env.example` if it doesn't already exist.

---

## 3. Configuration (`.env`)

Copy `.env.example` to `.env` (if not already created):

```bash
cp .env.example .env
```

### Choose Your Ingestion Source

Horizn supports three flexible ingestion sources out-of-the-box:

#### Option A: Full Apple Photos Library
Scans your system Photos library across a configurable time window:
```env
PHOTOS_LIBRARY_PATH=~/Pictures/Photos Library.photoslibrary
INGEST_BATCH_MONTHS=12
```

#### Option B: Dedicated Apple Photos Album (Recommended)
Create an album in Apple Photos (e.g. named `Horizn`) and add photos to it. Only photos in this album will be processed:
```env
PHOTOS_ALBUM_NAME=Horizn
```

#### Option C: Local Directory / Camera SD Card
Bypasses Apple Photos entirely and reads raw JPEGs/HEICs directly from a local folder or external drive:
```env
LOCAL_PHOTOS_DIR=/Users/username/Pictures/MyVacation
```

---

### Add Your API Keys

#### 1. Google Gemini API (Free Tier)
Horizn uses Gemini Flash for visual subject clustering, narrative sequencing, and evocative caption generation.
- Get a free key at [Google AI Studio](https://aistudio.google.com/).
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_FLASH_MODEL=gemini-3.1-flash-lite
GEMINI_PRO_MODEL=gemini-3.1-flash-lite
```

#### 2. Instagram Graph API (Publishing)
To publish carousels directly to your Instagram account:
- Refer to [Instagram Setup Guide](instagram_setup.md) for step-by-step instructions.
```env
META_APP_ID=your_meta_app_id
META_APP_SECRET=your_meta_app_secret
IG_USER_ID=your_ig_user_id
IG_ACCESS_TOKEN=your_long_lived_token
```

---

## 4. Running the Application

Launch both the backend and frontend simultaneously:

```bash
./scripts/start.sh
```

- **Web UI:** [http://localhost:5173](http://localhost:5173)
- **FastAPI Backend & Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

To stop the servers, press `Ctrl+C` in your terminal.
