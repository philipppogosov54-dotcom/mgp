#!/usr/bin/env python3
"""
Тест Решения 2: Сортировка отелей по релевантности.
"""
import asyncio
import sys
sys.path.insert(0, '/Users/lukiansilagadze/Desktop/Cursor mgp ai/_production_mgp')

from app.services.tourvisor import TourvisorService

async def test_sorting():
    """Тестируем сортировку по релевантности."""
    service = TourvisorService()
    
    print("=" * 60)
    print("🧪 ТЕСТ 1: Titanic Deluxe Belek")
    print("=" * 60)
    
    results = await service.find_hotel_by_name("Titanic Deluxe Belek", country="Турция")
    
    print(f"\n📊 Найдено отелей: {len(results)}")
    print("\n🏨 Порядок после сортировки:")
    for i, hotel in enumerate(results[:5], 1):
        score = service._score_hotel_relevance(hotel.name, "Titanic Deluxe Belek")
        print(f"   {i}. {hotel.name} ({hotel.stars}*) - Score: {score}")
    
    # Проверяем что Belek первый
    if results:
        first_hotel = results[0].name.lower()
        if "belek" in first_hotel:
            print("\n✅ PASS: Отель с 'Belek' на первом месте!")
        else:
            print(f"\n❌ FAIL: Первый отель: {results[0].name}")
    
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 2: Rixos Premium Belek")
    print("=" * 60)
    
    results2 = await service.find_hotel_by_name("Rixos Premium Belek", country="Турция")
    
    print(f"\n📊 Найдено отелей: {len(results2)}")
    print("\n🏨 Порядок после сортировки:")
    for i, hotel in enumerate(results2[:5], 1):
        score = service._score_hotel_relevance(hotel.name, "Rixos Premium Belek")
        print(f"   {i}. {hotel.name} ({hotel.stars}*) - Score: {score}")
    
    if results2:
        first_hotel = results2[0].name.lower()
        if "premium belek" in first_hotel:
            print("\n✅ PASS: Rixos Premium Belek на первом месте!")
        else:
            print(f"\n❌ FAIL: Первый отель: {results2[0].name}")
    
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 3: Delphin Imperial (проверка что не ломаем обычный поиск)")
    print("=" * 60)
    
    results3 = await service.find_hotel_by_name("Delphin Imperial", country="Турция")
    
    print(f"\n📊 Найдено отелей: {len(results3)}")
    print("\n🏨 Порядок после сортировки:")
    for i, hotel in enumerate(results3[:5], 1):
        score = service._score_hotel_relevance(hotel.name, "Delphin Imperial")
        print(f"   {i}. {hotel.name} ({hotel.stars}*) - Score: {score}")
    
    if results3:
        first_hotel = results3[0].name.lower()
        if "delphin imperial" in first_hotel:
            print("\n✅ PASS: Delphin Imperial на первом месте!")
        else:
            print(f"\n⚠️ CHECK: Первый отель: {results3[0].name}")
    
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 4: Просто 'Rixos' (бренд без уточнения)")
    print("=" * 60)
    
    results4 = await service.find_hotel_by_name("Rixos", country="Турция")
    
    print(f"\n📊 Найдено отелей: {len(results4)}")
    print("\n🏨 Первые 5 после сортировки:")
    for i, hotel in enumerate(results4[:5], 1):
        score = service._score_hotel_relevance(hotel.name, "Rixos")
        print(f"   {i}. {hotel.name} ({hotel.stars}*) - Score: {score}")
    
    # Проверяем что отели с Rixos в начале названия первые
    if results4:
        first_hotel = results4[0].name.lower()
        if first_hotel.startswith("rixos"):
            print("\n✅ PASS: Отели начинающиеся с 'Rixos' первые!")
        else:
            print(f"\n⚠️ CHECK: Первый отель: {results4[0].name}")
    
    print("\n" + "=" * 60)
    print("📋 ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_sorting())
