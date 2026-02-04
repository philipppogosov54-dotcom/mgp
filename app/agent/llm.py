"""
Клиент YandexGPT для ИИ-ассистента МГП.

Предоставляет методы для:
- Извлечения сущностей из текста (страна, даты, туристы)
- Определения намерения пользователя
- Ответов на FAQ вопросы
"""
from __future__ import annotations

import asyncio
import json
import logging
import httpx
from typing import Optional
from datetime import date

from app.core.config import settings

logger = logging.getLogger(__name__)


# Системный промпт для извлечения сущностей
# ANTI-HALLUCINATION PROMPT v2.0
ENTITY_EXTRACTION_PROMPT = """Ты — ИИ-ассистент туристического агентства. Твоя задача — извлечь ТОЛЬКО ту информацию, которая ЯВНО указана в сообщении пользователя.

=== КРИТИЧЕСКИЕ ПРАВИЛА (СТРОГО ОБЯЗАТЕЛЬНЫ!) ===

🚫 ЗАПРЕЩЕНО ГАЛЛЮЦИНИРОВАТЬ:
- НЕ придумывай date_from, если пользователь НЕ указал дату!
- НЕ придумывай adults, если пользователь НЕ указал количество людей!
- НЕ придумывай departure_city, если пользователь НЕ указал город вылета!
- НЕ подставляй дефолты ("01.01", "1 человек", "Москва")!

✅ ПРАВИЛО: Если параметр НЕ указан в тексте — НЕ включай его в JSON!

=== ПРИМЕРЫ ===

Пользователь: "хочу в турцию"
ПРАВИЛЬНО: {{"intent": "search_tour", "entities": {{"destination_country": "Турция"}}}}
НЕПРАВИЛЬНО: {{"intent": "search_tour", "entities": {{"destination_country": "Турция", "adults": 1, "date_from": "2026-01-01"}}}}

Пользователь: "турция на двоих"
ПРАВИЛЬНО: {{"intent": "search_tour", "entities": {{"destination_country": "Турция", "adults": 2}}}}

Пользователь: "египет 15 февраля"
ПРАВИЛЬНО: {{"intent": "search_tour", "entities": {{"destination_country": "Египет", "date_from": "2026-02-15"}}}}

=== ЧТО ИЗВЛЕКАТЬ (только если ЯВНО указано!) ===
- destination_country: страна назначения
- destination_region: регион (если указан)
- destination_resort: курорт (если указан)
- date_from: дата начала в формате YYYY-MM-DD (ТОЛЬКО если дата указана!)
- date_to: дата окончания в формате YYYY-MM-DD
- nights: количество ночей (ТОЛЬКО если указано "на 5 ночей", "на неделю" и т.д.)
- adults: количество взрослых (ТОЛЬКО если указано "вдвоём", "2 человека", "один" и т.д.)
- children: список возрастов детей (ТОЛЬКО если указаны дети с возрастом!)
- hotel_name: название отеля (если указан конкретный отель)
- food_type: тип питания (RO, BB, HB, FB, AI, UAI) — только если указано
- departure_city: город вылета (ТОЛЬКО если указан "из Москвы", "вылет из СПб" и т.д.)
- search_mode: режим поиска ("hotel_only" если "без перелета/только отель/пансионат")

=== INTENT (намерение) ===
- "search_tour" — пользователь ищет тур
- "hot_tours" — горящие туры ("горящий", "срочно", "ближайший вылет")
- "hotel_only" — только отель без перелёта ("без перелета", "только отель", "пансионат")
- "general_chat" — общий вопрос (погода, советы, сравнения)
- "faq_visa" — вопрос о визах
- "faq_payment" — вопрос об оплате
- "faq_cancel" — вопрос об отмене/возврате
- "faq_insurance" — вопрос о страховке
- "faq_documents" — вопрос о документах
- "greeting" — приветствие ("привет", "здравствуйте")
- "other" — другое

=== ДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА ===
1. Текущий год: {current_year}. Если год не указан, используй ближайшую БУДУЩУЮ дату.
2. "вдвоём", "для двоих" → adults: 2 (это ЯВНОЕ указание!)
3. "один", "одна", "сам" → adults: 1 (это ЯВНОЕ указание!)
4. "с ребенком 5 лет" → children: [5] (ТОЛЬКО если указан возраст!)
5. Если указан отель — НЕ требуй звёздность.

=== СЕМАНТИКА СОСТАВА ТУРИСТОВ (ВАЖНО!) ===
- "я" / "один" / "одна" / "сам" → adults: 1
- "мы с мужем" / "мы с женой" / "вдвоём" / "нас двое" → adults: 2
- "я и сын" / "я с ребенком" → adults: 1, children_mentioned: true (нужен возраст!)
- "я и дочь 7 лет" → adults: 1, children: [7]
- "мы с детьми" / "семьёй" → adults: 2, children_mentioned: true (нужен возраст!)
- "втроём с ребенком" → adults: 2, children_mentioned: true
- "семья из 4" → adults: 2, children_mentioned: true, children_count_mentioned: 2

=== OUTPUT FORMAT (СТРОГО!) ===
Output ONLY raw JSON. No markdown like ```json```. No intro. No outro.
Just a valid JSON object starting with {{ and ending with }}.

Верни ТОЛЬКО валидный JSON:
{{
  "intent": "search_tour",
  "entities": {{
    "destination_country": "Турция"
  }}
}}"""

# База знаний FAQ
FAQ_KNOWLEDGE_BASE = """
# База знаний туристического агентства МГП

## Визы и въезд

### Безвизовые страны для граждан РФ:
- **Турция** — до 60 дней без визы
- **Египет** — виза по прилёту (25$) или безвизовый въезд в Шарм-эль-Шейх до 15 дней
- **ОАЭ** — до 90 дней без визы
- **Таиланд** — до 30 дней без визы (можно продлить до 60)
- **Мальдивы** — до 30 дней без визы
- **Индонезия (Бали)** — до 30 дней без визы
- **Шри-Ланка** — электронная виза (ETA)
- **Куба** — до 30 дней без визы
- **Доминикана** — до 30 дней без визы
- **Черногория** — до 30 дней без визы

### Страны, требующие визу:
- **Шенген** (Греция, Испания, Италия, Франция и др.) — требуется шенгенская виза
- **Кипр** — бесплатная провиза онлайн (для граждан РФ)
- **США, Великобритания, Австралия** — требуется виза

### Требования к загранпаспорту:
- Срок действия: минимум 6 месяцев после даты возвращения
- Наличие чистых страниц для штампов

## Оплата туров

### Способы оплаты:
- Банковские карты (Visa, MasterCard, МИР)
- Наличные в офисе агентства
- Банковский перевод
- Система быстрых платежей (СБП)

### Рассрочка:
- Рассрочка 0% на 4-6 месяцев от банков-партнёров
- Первоначальный взнос от 10%

### Бронирование:
- Предоплата от 30% для подтверждения бронирования
- Полная оплата за 14 дней до вылета (для раннего бронирования)
- Горящие туры — полная оплата сразу

## Отмена и возврат

### Условия отмены тура:
- **Более 30 дней до вылета** — возврат 90-100% (за вычетом фактических расходов)
- **15-30 дней** — удержание до 25%
- **7-14 дней** — удержание до 50%
- **3-7 дней** — удержание до 75%
- **Менее 3 дней** — возврат не гарантирован

### Страховка от невыезда:
- Покрывает отмену по болезни, отказу в визе, вызову в суд и др.
- Стоимость: 3-5% от стоимости тура
- Рекомендуем оформлять при раннем бронировании

## Страхование

### Обязательная медицинская страховка:
- Включена в стоимость большинства пакетных туров
- Покрытие от 30 000 до 50 000 USD
- Покрывает: экстренную мед. помощь, госпитализацию, эвакуацию

### Дополнительные страховки:
- **Страховка от невыезда** — отмена по уважительным причинам
- **Страховка багажа** — потеря, повреждение багажа
- **Страховка от несчастных случаев** — травмы во время отдыха
- **Страховка активного отдыха** — дайвинг, серфинг, лыжи

## Документы для поездки

### Взрослые:
- Загранпаспорт (срок действия 6+ месяцев)
- Авиабилеты и ваучер отеля
- Страховой полис
- Копия внутреннего паспорта

### Дети:
- Загранпаспорт ребёнка (или запись в паспорте родителя для детей до 14 лет)
- Свидетельство о рождении (копия)
- Согласие на выезд от второго родителя (если едет с одним родителем)

### Для отдельных стран:
- Обратные билеты (подтверждение выезда)
- Бронирование отеля
- Подтверждение финансовой состоятельности
"""

# Промпт для ответов на FAQ
FAQ_ANSWER_PROMPT = """Ты — вежливый ИИ-ассистент туристического агентства МГП.
Используй ТОЛЬКО информацию из базы знаний для ответа на вопрос.
Отвечай кратко, по существу, дружелюбно.
Если информации нет в базе знаний — скажи, что нужно уточнить у менеджера.

База знаний:
{knowledge_base}

Вопрос пользователя: {question}

Дай полезный ответ:"""


class YandexGPTClient:
    """
    Клиент для работы с YandexGPT API.
    """
    
    BASE_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1"
    
    def __init__(self):
        self.folder_id = settings.YANDEX_FOLDER_ID
        self.api_key = settings.YANDEX_API_KEY
        self.model = settings.YANDEX_MODEL
        self.enabled = settings.YANDEX_GPT_ENABLED
        self.client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Ленивая инициализация HTTP клиента."""
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=60.0)
        return self.client
    
    async def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        max_retries: int = 3
    ) -> str:
        """
        Вызов YandexGPT API с exponential backoff retry.
        
        Args:
            system_prompt: Системный промпт
            user_prompt: Сообщение пользователя
            temperature: Температура генерации (0-1)
            max_tokens: Максимум токенов в ответе
            max_retries: Максимум попыток (по умолчанию 3)
            
        Returns:
            Текст ответа модели
            
        Raises:
            ValueError: Если YandexGPT не настроен
            Exception: После исчерпания всех попыток
        """
        if not self.enabled or not self.api_key or not self.folder_id:
            raise ValueError("YandexGPT не настроен. Проверьте YANDEX_API_KEY и YANDEX_FOLDER_ID")
        
        client = await self._get_client()
        
        model_uri = f"gpt://{self.folder_id}/{self.model}"
        
        payload = {
            "modelUri": model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": str(max_tokens)
            },
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_prompt}
            ]
        }
        
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    f"{self.BASE_URL}/completion",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                
                result = response.json()
                return result["result"]["alternatives"][0]["message"]["text"]
                
            except httpx.HTTPStatusError as e:
                last_exception = e
                # Не ретраим на клиентских ошибках (400-499)
                if 400 <= e.response.status_code < 500:
                    logger.warning(f"YandexGPT client error ({e.response.status_code}): {e}")
                    raise
                    
                # Серверные ошибки (500+) - ретраим
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(f"YandexGPT server error ({e.response.status_code}), retry {attempt + 1}/{max_retries} in {wait_time}s")
                await asyncio.sleep(wait_time)
                
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_exception = e
                wait_time = 2 ** attempt
                logger.warning(f"YandexGPT connection error: {e}, retry {attempt + 1}/{max_retries} in {wait_time}s")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                last_exception = e
                logger.error(f"YandexGPT unexpected error: {e}")
                raise
        
        # Все попытки исчерпаны
        logger.error(f"YandexGPT failed after {max_retries} retries: {last_exception}")
        raise last_exception
    
    def _clean_json_response(self, response: str) -> str:
        """
        Очистка ответа от markdown форматирования и лишних символов.
        
        STRICT JSON PARSER: Удаляет ```json```, вводный текст и концовки.
        """
        import re
        
        response = response.strip()
        
        # Удаляем markdown code blocks
        if "```" in response:
            # Ищем содержимое между ```json и ```
            pattern = r'```(?:json)?\s*([\s\S]*?)```'
            match = re.search(pattern, response)
            if match:
                response = match.group(1).strip()
            else:
                # Если нет закрывающего ``` — берём всё после ```json
                if response.startswith("```"):
                    parts = response.split("```")
                    if len(parts) > 1:
                        response = parts[1]
                        if response.startswith("json"):
                            response = response[4:]
        
        response = response.strip()
        
        # Удаляем вводный текст перед JSON
        # Например: "Вот JSON:\n{...}" или "Response: {...}"
        json_start = response.find('{')
        if json_start > 0:
            response = response[json_start:]
        
        # Удаляем текст после JSON
        # Находим последнюю закрывающую скобку
        json_end = response.rfind('}')
        if json_end != -1 and json_end < len(response) - 1:
            response = response[:json_end + 1]
        
        return response.strip()
    
    async def extract_entities(self, user_message: str) -> dict:
        """
        Извлечение сущностей из сообщения пользователя.
        
        Args:
            user_message: Текст сообщения
            
        Returns:
            Словарь с intent и entities
        """
        if not self.enabled:
            # Возвращаем пустой результат если LLM отключен
            return {"intent": "search_tour", "entities": {}}
        
        try:
            current_year = date.today().year
            system_prompt = ENTITY_EXTRACTION_PROMPT.format(current_year=current_year)
            
            response = await self._call_api(
                system_prompt=system_prompt,
                user_prompt=user_message,
                temperature=0.1,
                max_tokens=500
            )
            
            # Парсим JSON из ответа — STRICT JSON PARSER
            response = self._clean_json_response(response)
            
            result = json.loads(response)
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}, response: {response[:200] if response else 'None'}")
            # Попытка извлечь JSON из ответа
            try:
                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    result = json.loads(json_match.group())
                    return result
            except Exception:
                pass
            return {"intent": "search_tour", "entities": {}}
        except Exception as e:
            logger.error(f"YandexGPT extract_entities error: {e}")
            return {"intent": "search_tour", "entities": {}}
    
    async def answer_faq(self, question: str) -> str:
        """
        Ответ на FAQ вопрос с использованием базы знаний.
        
        Args:
            question: Вопрос пользователя
            
        Returns:
            Ответ на основе базы знаний
        """
        if not self.enabled:
            return ""
        
        try:
            prompt = FAQ_ANSWER_PROMPT.format(
                knowledge_base=FAQ_KNOWLEDGE_BASE,
                question=question
            )
            
            response = await self._call_api(
                system_prompt="Ты — полезный ассистент турагентства.",
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=800
            )
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"YandexGPT FAQ error: {e}")
            return ""
    
    async def generate_conversational_response(
        self,
        user_message: str,
        search_params: dict,
        conversation_history: list
    ) -> str:
        """
        Генерация разговорного ответа на общий вопрос.
        
        Отвечает на вопросы о погоде, советы по отелям, сравнения стран
        и мягко подводит к сбору информации для поиска тура.
        
        Args:
            user_message: Вопрос пользователя
            search_params: Уже известные параметры поиска
            conversation_history: История сообщений
            
        Returns:
            Ответ с информацией + мягкий вопрос о планах
        """
        if not self.enabled:
            return ""
        
        try:
            # Импортируем промпт здесь, чтобы избежать циклических импортов
            from app.agent.prompts import get_general_chat_prompt, get_system_prompt
            
            # Формируем промпт с контекстом
            chat_prompt = get_general_chat_prompt(user_message, search_params)
            system_prompt = get_system_prompt()
            
            # Формируем историю для контекста (последние 4 сообщения)
            recent_history = conversation_history[-4:] if len(conversation_history) > 4 else conversation_history
            history_text = "\n".join([
                f"{'Пользователь' if msg['role'] == 'user' else 'Ассистент'}: {msg['content']}"
                for msg in recent_history[:-1]  # Исключаем текущее сообщение
            ])
            
            if history_text:
                chat_prompt = f"История диалога:\n{history_text}\n\n{chat_prompt}"
            
            response = await self._call_api(
                system_prompt=system_prompt,
                user_prompt=chat_prompt,
                temperature=0.7,  # Более творческие ответы для разговора
                max_tokens=600
            )
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"YandexGPT conversational error: {e}")
            return ""
    
    async def close(self):
        """Закрытие HTTP клиента."""
        if self.client:
            await self.client.aclose()
            self.client = None


# Глобальный экземпляр клиента
llm_client = YandexGPTClient()
