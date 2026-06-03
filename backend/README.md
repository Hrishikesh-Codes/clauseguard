---
title: ClauseGuard API
emoji: 📄
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# ClauseGuard API

FastAPI backend for [ClauseGuard](https://tryclauseguard.vercel.app) — a lease and contract plain-English explainer.

This Space hosts the API only. It parses uploaded PDFs with pdfplumber, extracts clauses, and analyzes them with Groq (Llama 3.3 70B).

## Endpoints

- `GET /api/health` — health check
- `POST /api/analyze` — upload a PDF, returns clause-by-clause analysis, safety score, and lease summary

## Environment variables

Set these as **Secrets** in the Space settings:

- `GROQ_API_KEY` — your Groq API key
- `FRONTEND_URL` — the deployed frontend URL (for CORS)
