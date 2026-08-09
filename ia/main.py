from fastapi import FastAPI
import os

app = FastAPI(title="Kolia IA (placeholder)")


@app.get("/")
async def root():
    return {"message": "Kolia IA FastAPI placeholder"}


@app.get("/health")
async def health():
    return {"status": "ok"}
