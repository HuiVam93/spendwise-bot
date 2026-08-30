import os
import sqlite3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from fastapi import HTTPException

DB_NAME = os.getenv("DB_PATH", "/app/data/spendwise.db")

app = FastAPI()
app.mount("/webapp", StaticFiles(directory="webapp", html=True), name="webapp")

# Разрешаем запросы с GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_conn():
    return sqlite3.connect(DB_NAME)

class EnvelopeOut(BaseModel):
    id: int
    name: str
    icon: str
    budget: int
    spent: int
    remaining: int
    percent: int

class DashboardOut(BaseModel):
    total_budget: int
    total_spent: int
    remaining: int
    envelopes_count: int
    transactions_count: int
    envelopes: List[EnvelopeOut]

class TransactionIn(BaseModel):
    envelope_id: int
    amount: int
    note: str = ""


@app.post("/api/user/{user_id}/transaction")
async def add_transaction(user_id: int, payload: TransactionIn):
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT id FROM envelopes WHERE id = ? AND user_id = ?", (payload.envelope_id, user_id))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Envelope not found")

    if payload.amount <= 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Amount must be positive")

    c.execute(
        "INSERT INTO transactions (envelope_id, amount, note, created_at) VALUES (?, ?, ?, ?)",
        (payload.envelope_id, payload.amount, payload.note, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    return {"status": "ok"}

@app.get("/api/user/{user_id}/dashboard", response_model=DashboardOut)
async def get_dashboard(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    
    c.execute("SELECT COALESCE(SUM(budget), 0) FROM envelopes WHERE user_id = ?", (user_id,))
    total_budget = c.fetchone()[0]
    
    c.execute('''SELECT COALESCE(SUM(t.amount), 0) 
                 FROM transactions t
                 JOIN envelopes e ON t.envelope_id = e.id
                 WHERE e.user_id = ?''', (user_id,))
    total_spent = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM envelopes WHERE user_id = ?", (user_id,))
    env_count = c.fetchone()[0]
    
    c.execute('''SELECT COUNT(*) FROM transactions t
                 JOIN envelopes e ON t.envelope_id = e.id
                 WHERE e.user_id = ?''', (user_id,))
    trans_count = c.fetchone()[0]
    
    c.execute("SELECT id, name, icon, budget FROM envelopes WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    
    envelopes = []
    for row in rows:
        env_id, name, icon, budget = row
        c.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE envelope_id = ?", (env_id,))
        spent = c.fetchone()[0]
        remaining = budget - spent
        percent = min(int((spent / budget) * 100), 100) if budget > 0 else 0
        envelopes.append({
            "id": env_id,
            "name": name,
            "icon": icon,
            "budget": budget,
            "spent": spent,
            "remaining": remaining,
            "percent": percent
        })
    
    conn.close()
    
    return {
        "total_budget": total_budget,
        "total_spent": total_spent,
        "remaining": total_budget - total_spent,
        "envelopes_count": env_count,
        "transactions_count": trans_count,
        "envelopes": envelopes
    }
