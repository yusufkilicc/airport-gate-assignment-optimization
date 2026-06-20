# Deployment guide

The dashboard is a standard WSGI app (`server = app.server` in `src/dashboard.py`),
so any Python host that runs `gunicorn` can serve it. Below are turnkey steps for the
two recommended free options.

Both load precomputed results from `data/processed/` and `outputs/` at startup, so the
app boots in ~1–2 s. Those CSVs are committed to the repo. To refresh them, run
`python src/run_project.py` and commit the changes.

---

## Option A — Render (easiest)

Render reads `render.yaml` and `Procfile` automatically.

1. Push this repo to GitHub (see "First push" below).
2. Go to <https://dashboard.render.com> → **New** → **Blueprint**.
3. Connect your GitHub account and pick this repository.
4. Render detects `render.yaml`, creates a free Web Service, and runs:
   ```
   pip install -r requirements.txt
   gunicorn --chdir src dashboard:server --bind 0.0.0.0:$PORT --workers 1 --timeout 120
   ```
5. First build takes a few minutes. You get a public URL like
   `https://airport-gate-optimization.onrender.com`.

> Free tier note: the service **sleeps after ~15 min of inactivity**; the next visit
> takes ~30 s to wake. Fine for a portfolio demo. Upgrade the plan to keep it always-on.

---

## Option B — Hugging Face Spaces (always-on, Docker)

1. Push this repo to GitHub.
2. Create a Space: <https://huggingface.co/new-space> → **SDK: Docker** → **Blank**.
3. In the Space, add this front matter to the **top of its `README.md`** so HF knows
   the port (the `Dockerfile` already listens on 7860):
   ```yaml
   ---
   title: Airport Gate Optimization
   sdk: docker
   app_port: 7860
   ---
   ```
4. Push the code to the Space, either by adding the Space as a git remote:
   ```bash
   git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
   git push space main
   ```
   …or by uploading files in the Space's web UI.
5. HF builds the `Dockerfile` and serves the app at
   `https://<your-username>-<space-name>.hf.space`.

---

## First push to GitHub

From the project root:

```bash
git init
git add .
git commit -m "Airport gate allocation framework + deployable dashboard"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

`venv/`, caches, and the local academic working copies are excluded via `.gitignore`.

---

## Local production-mode test (optional)

Before deploying you can run exactly what the host runs:

```bash
pip install -r requirements.txt
gunicorn --chdir src dashboard:server --bind 0.0.0.0:8050 --workers 1 --timeout 120
```

Then open <http://127.0.0.1:8050>. (On Windows, `gunicorn` does not run natively — use
`python src/dashboard.py` for local testing and rely on the cloud host for gunicorn.)
