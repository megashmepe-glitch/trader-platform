import os, json, asyncio
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Models ──────────────────────────────────────────────────────
class Trade(BaseModel):
    date: str; instrument: str; direction: str; entry: float
    sl: float = 0; tp: float = 0; exit_price: float = 0; volume: float = 1
    pnl: float; setup: str = ""; discipline: str = "Да"; emotion: int = 3; notes: str = ""

class AgentTask(BaseModel):
    task: str; platform: str = "tiktok"; rounds: int = 2

class PsychEntry(BaseModel):
    date: str; mood: str; mistake: str = ""; win_moment: str = ""
    lesson: str = ""; violations: list = []

_trades: list = []
_psych: list = []

# ── Health ──────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

# ── Trades ──────────────────────────────────────────────────────
@app.get("/api/trades")
def get_trades(): return {"trades": _trades}

@app.post("/api/trades")
def add_trade(t: Trade):
    d = t.dict(); d["id"] = int(datetime.now().timestamp()*1000)
    _trades.append(d); return {"ok": True, "trade": d}

@app.delete("/api/trades/{tid}")
def del_trade(tid: int):
    global _trades; _trades = [t for t in _trades if t.get("id") != tid]
    return {"ok": True}

@app.get("/api/stats")
def get_stats():
    if not _trades: return {"total":0,"wins":0,"losses":0,"win_rate":0,"total_pnl":0}
    wins = [t for t in _trades if t["pnl"]>0]
    pnl  = sum(t["pnl"] for t in _trades)
    return {"total":len(_trades),"wins":len(wins),"losses":len(_trades)-len(wins),
            "win_rate":round(len(wins)/len(_trades)*100,1),"total_pnl":round(pnl,2)}

# ── Psych ───────────────────────────────────────────────────────
@app.get("/api/psych")
def get_psych(): return {"entries": _psych[-30:]}

@app.post("/api/psych")
def add_psych(e: PsychEntry):
    d = e.dict(); d["id"] = int(datetime.now().timestamp()*1000)
    _psych.append(d); return {"ok": True}

# ── Agents SSE ──────────────────────────────────────────────────
async def agent_stream(task, platform, rounds):
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    if not api_key:
        yield f"data: {json.dumps({'type':'error','text':'ANTHROPIC_API_KEY не задан'})}\n\n"; return

    client = anthropic.Anthropic(api_key=api_key)
    plats  = {"tiktok":"TikTok","instagram":"Instagram","twitter":"Twitter/X","telegram":"Telegram","youtube":"YouTube Shorts"}
    plat   = plats.get(platform,"TikTok")

    def sse(t,txt,extra=None):
        return f"data: {json.dumps({'type':t,'text':txt,**(extra or {})},ensure_ascii=False)}\n\n"

    def ask(system, user, tokens=1000):
        r = client.messages.create(model="claude-sonnet-4-6", max_tokens=tokens,
            system=system, messages=[{"role":"user","content":user}])
        return r.content[0].text.strip()

    try:
        yield sse("start", f"🚀 Задача: {task}", {"platform":plat})
        await asyncio.sleep(0.05)

        yield sse("agent_start","✍️ Генератор...",{"agent":"generator"})
        content = ask(f"Ты ГЕНЕРАТОР контента для {plat}. ХУК→ТЕЛО→CTA + хэштеги. Дерзко и конкретно.", f"Создай контент: {task}")
        yield sse("agent_done", content, {"agent":"generator"})
        await asyncio.sleep(0.05)

        critique = defense = ""
        for i in range(1, min(rounds,3)+1):
            yield sse("agent_start", f"🔥 Критик (раунд {i})...", {"agent":"critic"})
            critique = ask(f"Ты беспощадный КРИТИК для {plat}. Атакуй: хук, уникальность, CTA, алгоритмы, аудитория.",
                          f"Задача:{task}\nКонтент:\n{content}\nКритикуй!")
            yield sse("agent_done", critique, {"agent":"critic"})
            await asyncio.sleep(0.05)

            yield sse("agent_start", f"🛡️ Адвокат (раунд {i})...", {"agent":"advocate"})
            defense = ask("Ты АДВОКАТ. Защити контент. Опровергни критику с аргументами.",
                         f"Задача:{task}\nКонтент:\n{content}\nКритика:\n{critique}\nЗащищай!")
            yield sse("agent_done", defense, {"agent":"advocate"})
            await asyncio.sleep(0.05)

        yield sse("agent_start","⚡ Оптимизатор...",{"agent":"optimizer"})
        optimized = ask(f"Ты ОПТИМИЗАТОР для {plat}. Возьми лучшее из дебатов, создай финальную версию готовую к публикации.",
                       f"ОРИГИНАЛ:\n{content}\nКРИТИКА:\n{critique}\nЗАЩИТА:\n{defense}\nФинальная версия:")
        yield sse("agent_done", optimized, {"agent":"optimizer"})
        await asyncio.sleep(0.05)

        yield sse("agent_start","⚖️ Судья...",{"agent":"judge"})
        raw = ask("Оцени контент 0-10. Ответь:\nSCORE: [число]\nVERDICT: [1 предложение]",
                 f"Контент:\n{optimized}")
        score = 7.5; verdict = raw
        for line in raw.split("\n"):
            if line.startswith("SCORE:"):
                try: score=float(line.split(":")[1].strip())
                except: pass
            elif line.startswith("VERDICT:"):
                verdict = line.split(":",1)[1].strip()
        yield sse("agent_done", raw, {"agent":"judge"})
        yield sse("complete", optimized, {"score":score,"verdict":verdict,"original":content})

    except Exception as e:
        yield sse("error", f"Ошибка: {str(e)}")

@app.post("/api/agents/run")
async def run_agents(req: AgentTask):
    return StreamingResponse(agent_stream(req.task, req.platform, req.rounds),
        media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

# ── Frontend (HTML встроен чтобы не зависеть от папки static) ──
HTML = open(os.path.join(os.path.dirname(__file__), "static", "index.html"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(os.path.dirname(__file__), "static", "index.html")) \
    else "<h1>Trader Platform работает! Загрузи static/index.html на GitHub.</h1><p><a href='/api/health'>Health check</a></p>"

@app.get("/")
def root(): return HTMLResponse(HTML)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT",8000)))
