"""Интеграция с YandexGPT для генерации ответов."""

import httpx
from typing import Optional
from core.config import settings


class YandexGPTService:
    """Сервис для работы с YandexGPT API."""
    
    BASE_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1"
    
    def __init__(self):
        self.folder_id = settings.YANDEX_FOLDER_ID
        self.api_key = settings.YANDEX_API_KEY
        self.client = httpx.AsyncClient(timeout=60.0)
        self.model_uri = f"gpt://{self.folder_id}/yandexgpt-lite"
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1000
    ) -> str:
        """
        Генерация текста с помощью YandexGPT.
        
        Args:
            prompt: Запрос пользователя
            system_prompt: Системный промпт для контекста
            temperature: Температура генерации (0-1)
            max_tokens: Максимальное количество токенов в ответе
            
        Returns:
            Сгенерированный текст ответа
        """
        messages = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "text": system_prompt
            })
        
        messages.append({
            "role": "user",
            "text": prompt
        })
        
        payload = {
            "modelUri": self.model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": str(max_tokens)
            },
            "messages": messages
        }
        
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = await self.client.post(
                f"{self.BASE_URL}/completion",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            return result["result"]["alternatives"][0]["message"]["text"]
        except httpx.HTTPError as e:
            # TODO: Добавить логирование
            raise Exception(f"Ошибка YandexGPT API: {e}")
    
    async def close(self):
        """Закрытие HTTP клиента."""
        await self.client.aclose()
