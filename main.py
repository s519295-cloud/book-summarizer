import os
import re
import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

app = FastAPI()

# ---------- Конфигурация DeepSeek ----------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
) if DEEPSEEK_API_KEY else None
MODEL_NAME = "deepseek-chat"

# ---------- Тарифы DeepSeek (на 01.09.2026) ----------
PRICES = {
    "prompt": 0.14,      # $0.14 за 1M токенов ввода
    "completion": 0.28,  # $0.28 за 1M токенов вывода
}
USD_TO_RUB = 92.5  # актуальный курс

def calculate_cost(usage):
    prompt_tokens = usage.get('prompt_tokens', 0)
    completion_tokens = usage.get('completion_tokens', 0)
    total_tokens = usage.get('total_tokens', 0)

    cost_usd = (prompt_tokens / 1_000_000) * PRICES['prompt'] + (completion_tokens / 1_000_000) * PRICES['completion']
    cost_rub = cost_usd * USD_TO_RUB

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 6),
        "cost_rub": round(cost_rub, 4)
    }

# ---------- АГЕНТ-ПОИСКОВИК (через DeepSeek) ----------
def search_links_with_deepseek(title: str, author: str = None) -> list:
    if client is None:
        return []

    author_part = f" автора {author}" if author else ""
    prompt = f"""
Найди 5-10 ссылок, где можно бесплатно и полностью прочитать произведение "{title}"{author_part} на русском языке.
Верни ТОЛЬКО ссылки (URL), по одной на строке. Без пояснений, без номеров.

Пример ответа:
https://example.com/book
https://another-site.ru/text
"""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        text = response.choices[0].message.content.strip()
        links = [line.strip() for line in text.split('\n') if line.strip().startswith('http')]
        return links
    except Exception as e:
        print(f"Ошибка при поиске через DeepSeek: {e}")
        return []

def check_page_for_text(url: str, title: str, author: str = None) -> tuple:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        text = ' '.join(text.split())
        
        if len(text) < 1000:
            return False, f"Текст короткий ({len(text)} символов)"
        
        title_lower = re.sub(r'[^\w\s]', '', title).lower()
        title_words = title_lower.split()
        if not any(word in text.lower() for word in title_words):
            return False, "Название не найдено в тексте"
        
        if author:
            author_lower = author.lower()
            if author_lower not in text.lower():
                return False, f"Автор '{author}' не найден"
        
        return True, "OK"
    except Exception as e:
        return False, f"Ошибка: {e}"

def find_valid_links(title: str, author: str = None, max_links: int = 5) -> list:
    raw_links = search_links_with_deepseek(title, author)
    if not raw_links:
        return []
    
    raw_links = list(dict.fromkeys(raw_links))
    print(f"DeepSeek вернул {len(raw_links)} ссылок")
    
    valid = []
    for url in raw_links:
        if url.startswith('http'):
            print(f"Проверяем: {url}")
            is_valid, reason = check_page_for_text(url, title, author)
            if is_valid:
                valid.append(url)
                print(f"  ✅ Валидная")
                if len(valid) >= max_links:
                    break
            else:
                print(f"  ❌ Отбракована: {reason}")
    return valid

# ---------- АГЕНТ-ПЕРЕСКАЗЧИК ----------
def download_text_from_url(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        text = ' '.join(text.split())
        return text[:15000]
    except Exception as e:
        raise Exception(f"Не удалось скачать текст: {e}")

def summarize_text(text: str, title: str, depth: str = 'short') -> dict:
    if client is None:
        return {"summary": "❌ API-ключ DeepSeek не задан.", "usage": {}}
    if not text or len(text) < 100:
        return {"summary": "❌ Текст слишком короткий.", "usage": {}}

    depth_config = {
        'very_short': {'label': 'очень краткий (100–200 слов)', 'words': '100–200', 'instruction': 'Сделай максимально сжатый пересказ, только самая суть. Опиши главных героев, завязку и развязку в двух-трёх предложениях.'},
        'short': {'label': 'краткий (200–300 слов)', 'words': '200–300', 'instruction': 'Сделай краткий пересказ, выдели главных героев, основные события, завязку и развязку.'},
        'medium': {'label': 'средний (300–400 слов)', 'words': '300–400', 'instruction': 'Сделай содержательный пересказ с деталями. Опиши характеры героев, ключевые сцены, развитие сюжета.'},
        'detailed': {'label': 'подробный (400–500 слов)', 'words': '400–500', 'instruction': 'Сделай развёрнутый пересказ. Включи анализ поступков героев, их мотивы, ключевые диалоги и поворотные моменты.'},
        'deep': {'label': 'глубокий (500–700 слов)', 'words': '500–700', 'instruction': 'Сделай глубокий пересказ с элементами анализа. Добавь размышления о главной идее произведения, символизме, психологии персонажей и авторском замысле.'}
    }

    config = depth_config.get(depth, depth_config['short'])
    prompt = f"""
Ты — помощник для школьников. Сделай {config['label']} пересказ произведения "{title}".

Требования:
- Объём: {config['words']} слов.
- {config['instruction']}
- Пиши на русском языке, стиль — доступный и понятный школьникам.
- Не добавляй субъективных оценок, только факты и логику.

Текст произведения:
{text}

Пересказ:
"""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1200
        )
        summary = response.choices[0].message.content.strip()
        usage = response.usage.dict() if response.usage else {}
        return {"summary": summary, "usage": usage}
    except Exception as e:
        return {"summary": f"Ошибка ИИ: {e}", "usage": {}}

def generate_essay_plan(title: str, topic: str, summary: str) -> dict:
    if client is None:
        return {"plan": "❌ API-ключ DeepSeek не задан.", "usage": {}}
    prompt = f"""
Ты — помощник для школьников. Напиши план сочинения по произведению "{title}" на тему: "{topic}".

План должен содержать:
1. Вступление (введение в тему, постановка проблемы).
2. Основная часть (2-3 пункта, в которых раскрываются ключевые аспекты темы с опорой на текст произведения).
3. Заключение (вывод, итоговое размышление).

Не пиши само сочинение, только план. Каждый пункт должен быть коротким (1-2 предложения), но содержательным. Используй нумерацию.

Краткий пересказ произведения (для контекста):
{summary}

План сочинения:
"""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=600
        )
        plan = response.choices[0].message.content.strip()
        usage = response.usage.dict() if response.usage else {}
        return {"plan": plan, "usage": usage}
    except Exception as e:
        return {"plan": f"Ошибка ИИ: {e}", "usage": {}}

def write_essay(title: str, topic: str, plan: str, summary: str) -> dict:
    if client is None:
        return {"essay": "❌ API-ключ DeepSeek не задан.", "usage": {}}
    prompt = f"""
Ты — помощник для школьников. Напиши сочинение по произведению "{title}" на тему: "{topic}".

У тебя есть план сочинения:
{plan}

Используй этот план как структуру. Раскрой каждый пункт плана в связном тексте. Сочинение должно быть объёмом около 400–600 слов, стиль — литературный, доступный для школьников. Не переписывай план дословно, а создавай полноценный текст с вступлением, основной частью (по пунктам) и заключением.

Краткий пересказ произведения (для контекста):
{summary}

Сочинение:
"""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500
        )
        essay = response.choices[0].message.content.strip()
        usage = response.usage.dict() if response.usage else {}
        return {"essay": essay, "usage": usage}
    except Exception as e:
        return {"essay": f"Ошибка ИИ: {e}", "usage": {}}

# ---------- API-эндпоинты ----------
class SearchRequest(BaseModel):
    title: str
    author: str | None = None

class SummarizeRequest(BaseModel):
    url: str
    title: str
    depth: str = 'short'

class PlanRequest(BaseModel):
    title: str
    topic: str
    summary: str

class EssayRequest(BaseModel):
    title: str
    topic: str
    plan: str
    summary: str

@app.get("/", response_class=HTMLResponse)
def front():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/search")
def search_links_endpoint(request: SearchRequest):
    links = find_valid_links(request.title, request.author, max_links=5)
    if not links:
        raise HTTPException(status_code=404, detail="Не найдено ссылок с полным текстом. Попробуйте уточнить запрос.")
    return JSONResponse({"links": links})

@app.post("/summarize")
def summarize_endpoint(request: SummarizeRequest):
    try:
        text = download_text_from_url(request.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = summarize_text(text, request.title, request.depth)
    summary = result['summary']
    usage = result['usage']
    cost_info = calculate_cost(usage) if usage else {}
    return JSONResponse({
        "summary": summary,
        "usage": cost_info
    })

@app.post("/plan")
def plan_endpoint(request: PlanRequest):
    result = generate_essay_plan(request.title, request.topic, request.summary)
    plan = result['plan']
    usage = result['usage']
    cost_info = calculate_cost(usage) if usage else {}
    if not plan:
        raise HTTPException(status_code=500, detail="Не удалось сгенерировать план.")
    return JSONResponse({
        "plan": plan,
        "usage": cost_info
    })

@app.post("/write_essay")
def write_essay_endpoint(request: EssayRequest):
    result = write_essay(request.title, request.topic, request.plan, request.summary)
    essay = result['essay']
    usage = result['usage']
    cost_info = calculate_cost(usage) if usage else {}
    if not essay:
        raise HTTPException(status_code=500, detail="Не удалось сгенерировать сочинение.")
    return JSONResponse({
        "essay": essay,
        "usage": cost_info
    })

if __name__ == "__main__":
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="debug")