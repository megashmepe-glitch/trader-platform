# 🚀 ДЕПЛОЙ TRADER PLATFORM — Пошаговый гайд

## Что ты получишь
Один сайт по ссылке вида `https://твоё-имя.up.railway.app` с:
- 📋 Журналом трейдера
- 🤖 AI агентами (дебаты в реальном времени)
- 📈 Графиками и статистикой
- 🧠 Психологическим дневником

---

## ШАГ 1 — Получи API ключ Anthropic

1. Зайди на https://console.anthropic.com
2. Нажми **API Keys** → **Create Key**
3. Скопируй ключ — он начинается с `sk-ant-...`
4. СОХРАНИ его в блокноте (показывается один раз!)

---

## ШАГ 2 — Создай аккаунт на GitHub (если нет)

1. Зайди на https://github.com → Sign Up
2. Подтверди email

---

## ШАГ 3 — Загрузи файлы на GitHub

1. Нажми `+` → **New repository**
2. Название: `trader-platform`
3. Public/Private — любое
4. Нажми **Create repository**
5. Нажми **uploading an existing file**
6. Перетащи ВСЕ файлы из папки `trader_platform/`:
   - `main.py`
   - `requirements.txt`
   - `Procfile`
   - `railway.toml`
   - `nixpacks.toml`
   - `static/index.html`
7. Нажми **Commit changes**

---

## ШАГ 4 — Деплой на Railway (БЕСПЛАТНО)

1. Зайди на https://railway.app
2. Нажми **Start a New Project**
3. Выбери **Deploy from GitHub repo**
4. Дай доступ к GitHub → выбери `trader-platform`
5. Railway автоматически определит Python проект

### Добавь переменную окружения (API ключ):
1. В Railway нажми на твой проект
2. **Variables** → **Add Variable**
3. Имя: `ANTHROPIC_API_KEY`
4. Значение: `sk-ant-...твой-ключ...`
5. Нажми **Add**

6. Railway автоматически перезапустит и задеплоит
7. В разделе **Settings** → **Domains** нажми **Generate Domain**
8. Получишь ссылку типа `https://trader-platform-production.up.railway.app`

---

## ШАГ 5 — Открывай с любого устройства!

Просто открой ссылку в браузере на телефоне, планшете, компьютере.

---

## Если что-то не работает

**Статус-точка в шапке красная/жёлтая:**
- Бэкенд не запустился, проверь Variables — API ключ

**Агенты не отвечают:**
- Убедись что ANTHROPIC_API_KEY задан правильно
- Проверь https://твой-сайт.up.railway.app/api/health — должен вернуть `{"status":"ok"}`

**Бесплатный лимит Railway:**
- $5 кредит в месяц бесплатно (для личного использования хватит)
- При превышении — проект засыпает (можно разбудить)

---

## Апгрейды (потом)

- **Supabase** — подключи чтобы данные не терялись при перезапуске
- **Telegram бот** — получай готовый контент прямо в Telegram
- **Расписание** — агенты сами генерируют контент каждое утро
