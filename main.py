import os, json, asyncio, base64, textwrap, tempfile, math
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Trade(BaseModel):
    date: str; instrument: str; direction: str; entry: float
    sl: float = 0; tp: float = 0; exit_price: float = 0; volume: float = 1
    pnl: float; setup: str = ""; discipline: str = "Да"; emotion: int = 3; notes: str = ""

class AgentTask(BaseModel):
    task: str; platform: str = "tiktok"; rounds: int = 2

class PsychEntry(BaseModel):
    date: str; mood: str; mistake: str = ""; win_moment: str = ""
    lesson: str = ""; violations: list = []

class VideoRequest(BaseModel):
    script: str
    voice_id: str = "pNInz6obpgDQGcFmaJgB"  # Adam — хороший русский
    elevenlabs_key: str = ""

_trades: list = []
_psych:  list = []

@app.get("/api/health")
def health(): return {"status": "ok", "time": datetime.now().isoformat()}

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

@app.get("/api/psych")
def get_psych(): return {"entries": _psych[-30:]}

@app.post("/api/psych")
def add_psych(e: PsychEntry):
    d = e.dict(); d["id"] = int(datetime.now().timestamp()*1000)
    _psych.append(d); return {"ok": True}

# ── ТА Анализ ────────────────────────────────────────────────
@app.post("/api/analyze-chart")
async def analyze_chart(
    image: UploadFile = File(...),
    instrument: str = Form(""),
    timeframe: str = Form(""),
    question: str = Form(""),
):
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY не задан"}
    img_bytes = await image.read()
    img_b64   = base64.standard_b64encode(img_bytes).decode()
    mime      = image.content_type or "image/png"
    ctx = []
    if instrument: ctx.append(f"Инструмент: {instrument}")
    if timeframe:  ctx.append(f"Таймфрейм: {timeframe}")
    if question:   ctx.append(f"Вопрос: {question}")
    system = """Ты — опытный трейдер-ментор. Анализируй жёстко и конкретно.
Структура: 1)📊 Структура рынка 2)🎯 Ключевые уровни 3)⚠️ Ошибки в разметке 4)📍 Точка входа 5)💡 Советы"""
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(model="claude-sonnet-4-6", max_tokens=2000, system=system,
        messages=[{"role":"user","content":[
            {"type":"image","source":{"type":"base64","media_type":mime,"data":img_b64}},
            {"type":"text","text":"\n".join(ctx)+"\nПроанализируй график как ментор."}
        ]}])
    return {"analysis": resp.content[0].text}

# ── Генерация видео ───────────────────────────────────────────
def _make_srt(sentences: list[str], duration: float) -> str:
    """Создаёт SRT субтитры с равномерным распределением по времени."""
    srt = []
    per = duration / max(len(sentences), 1)
    for i, s in enumerate(sentences):
        start = i * per
        end   = (i + 1) * per - 0.1
        def fmt(t):
            h = int(t//3600); m = int((t%3600)//60)
            s2 = t % 60
            return f"{h:02d}:{m:02d}:{s2:06.3f}".replace(".",",")
        srt.append(f"{i+1}\n{fmt(start)} --> {fmt(end)}\n{s}\n")
    return "\n".join(srt)

def _split_script(script: str, max_chars: int = 60) -> list[str]:
    """Разбивает сценарий на строки субтитров."""
    sentences = []
    for line in script.replace("\n\n","\n").split("\n"):
        line = line.strip()
        if not line: continue
        # длинные строки бьём на куски
        if len(line) <= max_chars:
            sentences.append(line)
        else:
            words = line.split()
            chunk = []
            for w in words:
                chunk.append(w)
                if len(" ".join(chunk)) >= max_chars:
                    sentences.append(" ".join(chunk))
                    chunk = []
            if chunk:
                sentences.append(" ".join(chunk))
    return sentences or ["..."]

@app.post("/api/generate-video")
async def generate_video(req: VideoRequest):
    """Генерирует MP4: озвучка Edge TTS (бесплатно) + субтитры + ffmpeg."""
    import subprocess, edge_tts

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        audio_path = tmp / "voice.mp3"
        srt_path   = tmp / "subs.srt"
        video_path = tmp / "output.mp4"

        # ── 1. Озвучка через Microsoft Edge TTS (бесплатно) ──
        voice = req.voice_id  # передаём имя Edge TTS голоса
        communicate = edge_tts.Communicate(req.script, voice)
        await communicate.save(str(audio_path))

        # ── 2. Длительность аудио ────────────────────────────
        probe = subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True, text=True
        )
        try:
            duration = float(probe.stdout.strip())
        except Exception:
            duration = 30.0

        # ── 3. Субтитры ──────────────────────────────────────
        sentences = _split_script(req.script)
        srt_path.write_text(_make_srt(sentences, duration), encoding="utf-8")

        # ── 4. Сборка видео (1080x1920 TikTok формат) ────────
        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "color=c=0x0d1117:size=1080x1920:rate=25",
            "-i", str(audio_path),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            str(video_path)
        ], capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            return {"error": f"ffmpeg ошибка: {result.stderr[-500:]}"}

        # ── 5. Отдаём файл ───────────────────────────────────
        video_bytes = video_path.read_bytes()

    return StreamingResponse(
        iter([video_bytes]),
        media_type="video/mp4",
        headers={"Content-Disposition": "attachment; filename=tiktok_video.mp4"}
    )

# ── Agents SSE ───────────────────────────────────────────────
async def agent_stream(task, platform, rounds):
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    if not api_key:
        yield f"data: {json.dumps({'type':'error','text':'ANTHROPIC_API_KEY не задан'})}\n\n"; return
    client = anthropic.Anthropic(api_key=api_key)
    plats = {"tiktok":"TikTok","instagram":"Instagram","twitter":"Twitter/X","telegram":"Telegram","youtube":"YouTube Shorts"}
    plat  = plats.get(platform,"TikTok")
    def sse(t,txt,extra=None):
        return f"data: {json.dumps({'type':t,'text':txt,**(extra or {})},ensure_ascii=False)}\n\n"
    def ask(system, user, tokens=1000):
        r = client.messages.create(model="claude-sonnet-4-6", max_tokens=tokens,
            system=system, messages=[{"role":"user","content":user}])
        return r.content[0].text.strip()
    try:
        yield sse("start", f"🚀 Задача: {task}", {"platform":plat}); await asyncio.sleep(0.05)
        yield sse("agent_start","✍️ Генератор...",{"agent":"generator"})
        content = ask(f"Ты ГЕНЕРАТОР контента для {plat}. ХУК→ТЕЛО→CTA + хэштеги.", f"Создай контент: {task}")
        yield sse("agent_done", content, {"agent":"generator"}); await asyncio.sleep(0.05)
        critique = defense = ""
        for i in range(1, min(rounds,3)+1):
            yield sse("agent_start", f"🔥 Критик (раунд {i})...", {"agent":"critic"})
            critique = ask(f"Ты беспощадный КРИТИК для {plat}.", f"Задача:{task}\nКонтент:\n{content}\nКритикуй!")
            yield sse("agent_done", critique, {"agent":"critic"}); await asyncio.sleep(0.05)
            yield sse("agent_start", f"🛡️ Адвокат (раунд {i})...", {"agent":"advocate"})
            defense = ask("Ты АДВОКАТ. Защити контент.", f"Задача:{task}\nКонтент:\n{content}\nКритика:\n{critique}\nЗащищай!")
            yield sse("agent_done", defense, {"agent":"advocate"}); await asyncio.sleep(0.05)
        yield sse("agent_start","⚡ Оптимизатор...",{"agent":"optimizer"})
        optimized = ask(f"Ты ОПТИМИЗАТОР для {plat}. Создай финальную версию.",
                       f"ОРИГИНАЛ:\n{content}\nКРИТИКА:\n{critique}\nЗАЩИТА:\n{defense}\nФинал:")
        yield sse("agent_done", optimized, {"agent":"optimizer"}); await asyncio.sleep(0.05)
        yield sse("agent_start","⚖️ Судья...",{"agent":"judge"})
        raw = ask("Оцени 0-10.\nSCORE: [число]\nVERDICT: [1 предложение]", f"Контент:\n{optimized}")
        score = 7.5; verdict = raw
        for line in raw.split("\n"):
            if line.startswith("SCORE:"):
                try: score=float(line.split(":")[1].strip())
                except: pass
            elif line.startswith("VERDICT:"): verdict=line.split(":",1)[1].strip()
        yield sse("agent_done", raw, {"agent":"judge"})
        yield sse("complete", optimized, {"score":score,"verdict":verdict,"original":content})
    except Exception as e:
        yield sse("error", f"Ошибка: {str(e)}")

@app.post("/api/agents/run")
async def run_agents(req: AgentTask):
    return StreamingResponse(agent_stream(req.task, req.platform, req.rounds),
        media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

HTML = open(os.path.join(os.path.dirname(__file__), "static", "index.html"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(os.path.dirname(__file__), "static", "index.html")) \
    else "<h1>Загрузи static/index.html на GitHub</h1>"

@app.get("/")
def root(): return HTMLResponse(HTML)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT",8000)))
