"""
FastAPI бэкенд — Trader Platform
Включает: SSE стриминг агентов, CRUD для сделок, Supabase интеграция
"""
import os, json, asyncio
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Инициализация ──────────────────────────────────────────────
app = FastAPI(title="Trader Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ── Pydantic модели ────────────────────────────────────────────
class Trade(BaseModel):
    date: str
    instrument: str
    direction: str          # LONG / SHORT
    entry: float
    sl: float = 0
    tp: float = 0
    exit_price: float = 0
    volume: float = 1
    pnl: float
    setup: str = ""
    discipline: str = "Да"
    emotion: int = 3
    notes: str = ""

class AgentTask(BaseModel):
    task: str
    platform: str = "tiktok"   # tiktok/instagram/twitter/telegram
    rounds: int = 2             # 1-3 раунда дебатов

class PsychEntry(BaseModel):
    date: str
    mood: str
    discipline_score: int
    mistake: str = ""
    win_moment: str = ""
    lesson: str = ""
    violations: list[str] = []

# ── In-memory хранилище (заменить на Supabase если нужно) ──────
_trades: list[dict] = []
_psych:  list[dict] = []

# ── HEALTH CHECK ───────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

# ══════════════════════════════════════════════════════════════
# ТОРГОВЫЙ ЖУРНАЛ
# ══════════════════════════════════════════════════════════════

@app.get("/api/trades")
def get_trades():
    return {"trades": _trades}

@app.post("/api/trades")
def add_trade(trade: Trade):
    t = trade.dict()
    t["id"] = int(datetime.now().timestamp() * 1000)
    _trades.append(t)
    return {"ok": True, "trade": t}

@app.delete("/api/trades/{trade_id}")
def delete_trade(trade_id: int):
    global _trades
    _trades = [t for t in _trades if t.get("id") != trade_id]
    return {"ok": True}

@app.get("/api/stats")
def get_stats():
    if not _trades:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0}
    wins   = [t for t in _trades if t["pnl"] > 0]
    losses = [t for t in _trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in _trades)
    return {
        "total":     len(_trades),
        "wins":      len(wins),
        "losses":    len(losses),
        "win_rate":  round(len(wins) / len(_trades) * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_win":   round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0,
        "avg_loss":  round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0,
    }

# ══════════════════════════════════════════════════════════════
# ПСИХОЛОГИЧЕСКИЙ ДНЕВНИК
# ══════════════════════════════════════════════════════════════

@app.get("/api/psych")
def get_psych():
    return {"entries": _psych[-30:]}

@app.post("/api/psych")
def add_psych(entry: PsychEntry):
    e = entry.dict()
    e["id"] = int(datetime.now().timestamp() * 1000)
    _psych.append(e)
    return {"ok": True}

# ══════════════════════════════════════════════════════════════
# АГЕНТЫ — SSE СТРИМИНГ (вот где магия "без лагов")
# ══════════════════════════════════════════════════════════════

async def run_agents_stream(task: str, platform: str, rounds: int) -> AsyncGenerator[str, None]:
    """
    Генератор SSE событий.
    Каждый агент стримит свой ответ по мере готовности —
    пользователь видит прогресс в реальном времени, а не ждёт 30 сек.
    """
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        yield f"data: {json.dumps({'type':'error','text':'ANTHROPIC_API_KEY не задан'})}\n\n"
        return

    client = anthropic.Anthropic(api_key=api_key)

    PLATFORMS = {"tiktok":"TikTok","instagram":"Instagram","twitter":"Twitter/X",
                 "telegram":"Telegram","youtube":"YouTube Shorts"}
    plat = PLATFORMS.get(platform, "TikTok")

    def sse(event_type: str, text: str, extra: dict = None) -> str:
        data = {"type": event_type, "text": text, **(extra or {})}
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    def call_claude(system: str, user: str, max_tokens: int = 1200) -> str:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text.strip()

    try:
        # ── Старт ──
        yield sse("start", f"🚀 Запускаю агентов для: {task}", {"platform": plat})
        await asyncio.sleep(0.1)

        # ── Генератор ──
        yield sse("agent_start", "✍️ Генератор создаёт контент...", {"agent": "generator"})
        gen_prompt = f"""Ты — ГЕНЕРАТОР контента для {plat}.
Создай максимально цепляющий пост.
Структура: ХУК (1-2 строки) → ТЕЛО → CTA + хэштеги.
Задача: {task}"""
        content = call_claude(gen_prompt, f"Создай контент: {task}", 1000)
        yield sse("agent_done", content, {"agent": "generator"})
        await asyncio.sleep(0.1)

        critique = ""
        defense = ""

        # ── Раунды дебатов ──
        for round_num in range(1, min(rounds, 3) + 1):
            # Критик
            yield sse("agent_start", f"🔥 Критик атакует (раунд {round_num})...", {"agent": "critic"})
            crit_system = f"""Ты — беспощадный КРИТИК контента.
Найди ВСЕ слабые места: хук, уникальность, CTA, алгоритмы {plat}, аудитория.
Будь конкретным и жёстким. Никаких комплиментов."""
            critique = call_claude(crit_system, f"Задача: {task}\n\nКонтент:\n{content}\n\nКритикуй!", 800)
            yield sse("agent_done", critique, {"agent": "critic"})
            await asyncio.sleep(0.1)

            # Адвокат
            yield sse("agent_start", f"🛡️ Адвокат защищает (раунд {round_num})...", {"agent": "advocate"})
            adv_system = """Ты — АДВОКАТ. Защити контент от критики.
Найди реальные сильные стороны. Опровергни критику с аргументами."""
            defense = call_claude(adv_system,
                f"Задача: {task}\nКонтент:\n{content}\nКритика:\n{critique}\nЗащищай!", 700)
            yield sse("agent_done", defense, {"agent": "advocate"})
            await asyncio.sleep(0.1)

        # ── Оптимизатор ──
        yield sse("agent_start", "⚡ Оптимизатор синтезирует лучшее...", {"agent": "optimizer"})
        opt_system = f"""Ты — ОПТИМИЗАТОР для {plat}.
Возьми лучшее из дебатов (Критик + Адвокат) и создай финальную версию.
Усиль хук, исправь слабое, оставь сильное. Готово к публикации."""
        optimized = call_claude(opt_system,
            f"Задача: {task}\nОРИГИНАЛ:\n{content}\nКРИТИКА:\n{critique}\nЗАЩИТА:\n{defense}\n\nФинальная версия:",
            1200)
        yield sse("agent_done", optimized, {"agent": "optimizer"})
        await asyncio.sleep(0.1)

        # ── Судья ──
        yield sse("agent_start", "⚖️ Судья выносит вердикт...", {"agent": "judge"})
        judge_system = """Ты — СУДЬЯ. Оцени финальный контент по 10-балльной шкале.
Критерии: хук (0-2), содержание (0-2), CTA (0-2), вирусность (0-2), готовность (0-2).
Ответь СТРОГО:
SCORE: [0-10]
VERDICT: [1 предложение с причиной оценки]"""
        judge_raw = call_claude(judge_system,
            f"Оригинал:\n{content}\n\nФинал:\n{optimized}\n\nВердикт:", 400)

        score = 7.5
        verdict_text = judge_raw
        for line in judge_raw.split("\n"):
            if line.startswith("SCORE:"):
                try: score = float(line.split(":")[1].strip())
                except: pass
            elif line.startswith("VERDICT:"):
                verdict_text = line.split(":", 1)[1].strip()

        yield sse("agent_done", judge_raw, {"agent": "judge"})
        await asyncio.sleep(0.1)

        # ── Финал ──
        yield sse("complete", optimized, {
            "score": score,
            "verdict": verdict_text,
            "original": content,
        })

    except Exception as e:
        yield sse("error", f"Ошибка: {str(e)}")


@app.post("/api/agents/run")
async def run_agents(task_req: AgentTask):
    """SSE endpoint — стримит ответы агентов в реальном времени."""
    return StreamingResponse(
        run_agents_stream(task_req.task, task_req.platform, task_req.rounds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ── Раздача фронтенда ──────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
https://web-production-462b4.up.railway.app/
