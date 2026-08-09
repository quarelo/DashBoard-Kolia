from fastapi import FastAPI
import os

app = FastAPI(title="Kolia IA ")


@app.get("/")
async def root():
    return {"message": "Kolia IA FastAPI"}


@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/analisar")
async def  analisar():
    
