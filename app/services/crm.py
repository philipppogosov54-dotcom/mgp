"""
CRM сервис для сохранения заявок клиентов.

Простая реализация с сохранением в файл leads.txt.
В будущем можно заменить на интеграцию с реальной CRM.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

# Путь к файлу заявок
LEADS_FILE = Path(__file__).parent.parent.parent / "leads.txt"


async def save_lead(
    name: str,
    phone: str,
    search_params: str,
    tour_offer_id: Optional[str] = None
) -> str:
    """
    Сохраняет заявку клиента в файл leads.txt.
    
    Args:
        name: Имя клиента
        phone: Номер телефона
        search_params: Описание параметров поиска
        tour_offer_id: ID выбранного тура (если есть)
        
    Returns:
        ID созданной заявки
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lead_id = datetime.now().strftime("%Y%m%d%H%M%S")
    
    # Форматируем строку заявки
    lead_line = f"{timestamp} | ID:{lead_id} | {name} | {phone} | {search_params}"
    
    if tour_offer_id:
        lead_line += f" | Тур: {tour_offer_id}"
    
    lead_line += "\n"
    
    # Записываем в файл (создаём если не существует)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _write_lead, lead_line)
    
    return lead_id


def _write_lead(lead_line: str) -> None:
    """Синхронная запись в файл (выполняется в executor)."""
    # Создаём файл с заголовком, если не существует
    if not LEADS_FILE.exists():
        with open(LEADS_FILE, "w", encoding="utf-8") as f:
            f.write("# Заявки MGP AI Assistant\n")
            f.write("# Формат: Дата | ID | Имя | Телефон | Параметры поиска | Тур\n")
            f.write("=" * 80 + "\n")
    
    # Добавляем заявку
    with open(LEADS_FILE, "a", encoding="utf-8") as f:
        f.write(lead_line)


async def get_leads_count() -> int:
    """Возвращает количество сохранённых заявок."""
    if not LEADS_FILE.exists():
        return 0
    
    loop = asyncio.get_event_loop()
    count = await loop.run_in_executor(None, _count_leads)
    return count


def _count_leads() -> int:
    """Синхронный подсчёт заявок."""
    count = 0
    with open(LEADS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#") and not line.startswith("="):
                count += 1
    return count


async def get_recent_leads(limit: int = 10) -> list[dict]:
    """
    Возвращает последние заявки.
    
    Args:
        limit: Максимальное количество заявок
        
    Returns:
        Список заявок в виде словарей
    """
    if not LEADS_FILE.exists():
        return []
    
    loop = asyncio.get_event_loop()
    leads = await loop.run_in_executor(None, _read_recent_leads, limit)
    return leads


def _read_recent_leads(limit: int) -> list[dict]:
    """Синхронное чтение последних заявок."""
    leads = []
    
    with open(LEADS_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Парсим строки (пропускаем заголовки)
    for line in reversed(lines):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("="):
            continue
        
        parts = line.split(" | ")
        if len(parts) >= 4:
            lead = {
                "timestamp": parts[0],
                "id": parts[1].replace("ID:", "") if len(parts) > 1 else "",
                "name": parts[2] if len(parts) > 2 else "",
                "phone": parts[3] if len(parts) > 3 else "",
                "search_params": parts[4] if len(parts) > 4 else "",
                "tour_offer_id": parts[5].replace("Тур: ", "") if len(parts) > 5 else None
            }
            leads.append(lead)
            
            if len(leads) >= limit:
                break
    
    return leads
