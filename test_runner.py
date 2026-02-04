#!/usr/bin/env python3
"""
🧪 Test Runner с полным сохранением артефактов.

Запуск:
    python test_runner.py --scenarios scenarios.json --output test_results/

Структура выходных артефактов:
    test_results/
    └── run_2026-01-27_15-30-00/
        ├── summary.json              # Общая статистика прогона
        ├── scenario_001_турция/
        │   ├── chat_history.json     # Полная переписка
        │   ├── api_calls.json        # Все API вызовы
        │   └── state_snapshots.json  # Состояния между шагами
        ├── scenario_002_египет/
        │   └── ...
        └── comparison.json           # Сравнение с предыдущим прогоном (если есть)
"""

import json
import os
import sys
import time
import asyncio
import argparse
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import uuid
import requests


class TestArtifactCollector:
    """Сборщик артефактов для одного тестового сценария."""
    
    def __init__(self, scenario_name: str, output_dir: Path):
        self.scenario_name = scenario_name
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.conversation_id: Optional[str] = None
        self.chat_history: list[dict] = []
        self.api_calls: list[dict] = []
        self.state_snapshots: list[dict] = []
        self.errors: list[dict] = []
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
    
    def log_turn(
        self,
        turn_id: int,
        user_message: str,
        assistant_response: str,
        tour_cards: list[dict],
        response_time_ms: float,
        raw_response: dict
    ):
        """Логирование одного хода диалога."""
        self.chat_history.append({
            "turn_id": turn_id,
            "timestamp": datetime.now().isoformat(),
            "user_message": user_message,
            "assistant_response": assistant_response,
            "tour_cards_count": len(tour_cards),
            "tour_cards": tour_cards[:5],  # Только первые 5
            "response_time_ms": round(response_time_ms, 2),
            "conversation_id": self.conversation_id,
            # Состояние из ответа (если есть)
            "search_mode": raw_response.get("search_mode"),
            "cascade_stage": raw_response.get("cascade_stage"),
            "missing_info": raw_response.get("missing_info"),
        })
    
    def log_api_call(
        self,
        endpoint: str,
        request_params: dict,
        response_status: int,
        response_body: Any,
        elapsed_ms: float,
        error: Optional[str] = None
    ):
        """Логирование API вызова."""
        self.api_calls.append({
            "timestamp": datetime.now().isoformat(),
            "conversation_id": self.conversation_id,
            "endpoint": endpoint,
            "request_params": self._sanitize(request_params),
            "response_status": response_status,
            "response_body_preview": str(response_body)[:1000] if response_body else None,
            "elapsed_ms": round(elapsed_ms, 2),
            "error": error
        })
    
    def log_state_snapshot(self, turn_id: int, state: dict):
        """Снимок состояния после хода."""
        self.state_snapshots.append({
            "turn_id": turn_id,
            "timestamp": datetime.now().isoformat(),
            "search_params": self._sanitize(state.get("search_params", {})),
            "search_mode": state.get("search_mode"),
            "cascade_stage": state.get("cascade_stage"),
            "intent": state.get("intent"),
            "missing_info": state.get("missing_info"),
        })
    
    def log_error(self, error_type: str, error_message: str, context: dict = None):
        """Логирование ошибки."""
        self.errors.append({
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "error_message": error_message,
            "context": context,
            "traceback": traceback.format_exc()
        })
    
    def _sanitize(self, data: dict) -> dict:
        """Маскирование секретных данных."""
        if not data:
            return {}
        
        sensitive = {"authlogin", "authpass", "api_key", "token", "password"}
        result = {}
        for k, v in data.items():
            if any(s in k.lower() for s in sensitive):
                result[k] = "***MASKED***"
            elif isinstance(v, dict):
                result[k] = self._sanitize(v)
            else:
                result[k] = v
        return result
    
    def save(self) -> dict:
        """Сохранение всех артефактов в файлы."""
        self.end_time = datetime.now()
        
        # Chat history
        chat_file = self.output_dir / "chat_history.json"
        with open(chat_file, "w", encoding="utf-8") as f:
            json.dump(self.chat_history, f, ensure_ascii=False, indent=2)
        
        # API calls
        api_file = self.output_dir / "api_calls.json"
        with open(api_file, "w", encoding="utf-8") as f:
            json.dump(self.api_calls, f, ensure_ascii=False, indent=2)
        
        # State snapshots
        state_file = self.output_dir / "state_snapshots.json"
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(self.state_snapshots, f, ensure_ascii=False, indent=2)
        
        # Errors (если есть)
        if self.errors:
            errors_file = self.output_dir / "errors.json"
            with open(errors_file, "w", encoding="utf-8") as f:
                json.dump(self.errors, f, ensure_ascii=False, indent=2)
        
        # Summary для этого сценария
        summary = {
            "scenario_name": self.scenario_name,
            "conversation_id": self.conversation_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": (self.end_time - self.start_time).total_seconds(),
            "total_turns": len(self.chat_history),
            "total_api_calls": len(self.api_calls),
            "errors_count": len(self.errors),
            "final_tour_cards_count": self.chat_history[-1]["tour_cards_count"] if self.chat_history else 0,
        }
        
        summary_file = self.output_dir / "scenario_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        return summary


class TestRunner:
    """Запуск тестовых сценариев с сохранением артефактов."""
    
    def __init__(self, base_url: str = "http://localhost:8000", output_base: str = "test_results"):
        self.base_url = base_url
        self.output_base = Path(output_base)
        self.run_dir: Optional[Path] = None
        self.results: list[dict] = []
    
    def _create_run_dir(self) -> Path:
        """Создание директории для текущего прогона."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run_dir = self.output_base / f"run_{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    
    def run_scenario(self, scenario: dict) -> dict:
        """
        Запуск одного сценария.
        
        Args:
            scenario: {
                "name": "турция_базовый",
                "description": "Базовый поиск в Турцию",
                "messages": ["Хочу в Турцию из Москвы", "15 марта", "2 взрослых", "4 звезды AI"],
                "expected": {"tours_found": true, "min_tours": 1}
            }
        """
        name = scenario.get("name", f"scenario_{len(self.results)+1}")
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        scenario_dir = self.run_dir / f"scenario_{len(self.results)+1:03d}_{safe_name}"
        
        collector = TestArtifactCollector(name, scenario_dir)
        
        print(f"\n{'='*60}")
        print(f"🧪 Сценарий: {name}")
        print(f"   Описание: {scenario.get('description', '-')}")
        print(f"{'='*60}")
        
        conversation_id = None
        
        for turn_id, user_message in enumerate(scenario.get("messages", []), 1):
            print(f"\n[{turn_id}] 👤 User: {user_message}")
            
            try:
                start_time = time.time()
                
                response = requests.post(
                    f"{self.base_url}/api/v1/chat",
                    json={
                        "message": user_message,
                        "conversation_id": conversation_id
                    },
                    timeout=180
                )
                
                elapsed_ms = (time.time() - start_time) * 1000
                data = response.json()
                
                conversation_id = data.get("conversation_id")
                collector.conversation_id = conversation_id
                
                assistant_response = data.get("reply", "")
                tour_cards = data.get("tour_cards") or []
                
                print(f"    🤖 Assistant: {assistant_response[:100]}...")
                print(f"    📊 Туров: {len(tour_cards)} | Время: {elapsed_ms:.0f}ms")
                
                collector.log_turn(
                    turn_id=turn_id,
                    user_message=user_message,
                    assistant_response=assistant_response,
                    tour_cards=tour_cards,
                    response_time_ms=elapsed_ms,
                    raw_response=data
                )
                
            except Exception as e:
                print(f"    ❌ Error: {e}")
                collector.log_error("request_error", str(e), {"turn_id": turn_id})
        
        # Сохраняем артефакты
        summary = collector.save()
        
        # Проверяем ожидания
        expected = scenario.get("expected", {})
        passed = True
        
        if expected.get("tours_found") is not None:
            actual_found = summary["final_tour_cards_count"] > 0
            if actual_found != expected["tours_found"]:
                passed = False
                print(f"    ❌ Expected tours_found={expected['tours_found']}, got {actual_found}")
        
        if expected.get("min_tours") is not None:
            if summary["final_tour_cards_count"] < expected["min_tours"]:
                passed = False
                print(f"    ❌ Expected min_tours={expected['min_tours']}, got {summary['final_tour_cards_count']}")
        
        summary["passed"] = passed
        summary["expected"] = expected
        
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"\n{status} | Туров: {summary['final_tour_cards_count']} | Время: {summary['duration_seconds']:.1f}s")
        
        self.results.append(summary)
        return summary
    
    def run_all(self, scenarios: list[dict]) -> dict:
        """Запуск всех сценариев."""
        self.run_dir = self._create_run_dir()
        print(f"\n📁 Артефакты сохраняются в: {self.run_dir}")
        
        for scenario in scenarios:
            self.run_scenario(scenario)
        
        # Общий summary
        total = len(self.results)
        passed = sum(1 for r in self.results if r.get("passed"))
        failed = total - passed
        
        overall_summary = {
            "run_timestamp": datetime.now().isoformat(),
            "run_directory": str(self.run_dir),
            "total_scenarios": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{100*passed//total}%" if total > 0 else "N/A",
            "scenarios": self.results
        }
        
        # Сохраняем общий summary
        summary_file = self.run_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(overall_summary, f, ensure_ascii=False, indent=2)
        
        print(f"\n{'='*60}")
        print(f"📊 ИТОГИ ПРОГОНА")
        print(f"{'='*60}")
        print(f"   Всего: {total}")
        print(f"   ✅ Passed: {passed}")
        print(f"   ❌ Failed: {failed}")
        print(f"   Pass Rate: {overall_summary['pass_rate']}")
        print(f"\n📁 Артефакты: {self.run_dir}")
        
        return overall_summary


# Примеры сценариев
EXAMPLE_SCENARIOS = [
    {
        "name": "турция_базовый",
        "description": "Базовый поиск в Турцию с полными параметрами",
        "messages": [
            "Хочу в Турцию из Москвы 15 марта на неделю 2 взрослых 4 звезды всё включено"
        ],
        "expected": {"tours_found": True, "min_tours": 1}
    },
    {
        "name": "турция_пошаговый",
        "description": "Пошаговый сбор параметров",
        "messages": [
            "Хочу в Турцию",
            "Из Москвы",
            "15 марта",
            "На неделю",
            "Двое взрослых",
            "4 звезды всё включено"
        ],
        "expected": {"tours_found": True}
    },
    {
        "name": "горящие_египет",
        "description": "Горящие туры в Египет",
        "messages": [
            "Горящие туры в Египет из Москвы"
        ],
        "expected": {"tours_found": True}
    },
    {
        "name": "hotel_only_турция",
        "description": "Только проживание в Турции",
        "messages": [
            "Только проживание в Турции 20 марта неделя двое 5 звёзд ультра"
        ],
        "expected": {"tours_found": True}
    },
    {
        "name": "отель_rixos",
        "description": "Поиск конкретного отеля Rixos",
        "messages": [
            "Rixos Premium Belek Турция из Москвы 20 марта неделя 2 взр 5 звёзд ультра"
        ],
        "expected": {"tours_found": True}
    },
    {
        "name": "даты_середина_марта",
        "description": "Относительная дата - середина марта",
        "messages": [
            "Турция из Москвы в середине марта неделя 2 взр 4 звезды AI"
        ],
        "expected": {"tours_found": True}
    },
]


class RunComparator:
    """Сравнение двух прогонов для обнаружения регрессий."""
    
    def __init__(self, baseline_dir: Path, current_dir: Path):
        self.baseline_dir = Path(baseline_dir)
        self.current_dir = Path(current_dir)
        self.regressions: list[dict] = []
        self.improvements: list[dict] = []
        self.unchanged: list[dict] = []
    
    def compare(self) -> dict:
        """Сравнение двух прогонов."""
        print(f"\n{'='*60}")
        print(f"🔍 СРАВНЕНИЕ ПРОГОНОВ")
        print(f"{'='*60}")
        print(f"   Baseline: {self.baseline_dir.name}")
        print(f"   Current:  {self.current_dir.name}")
        print(f"{'='*60}")
        
        # Загружаем summary обоих прогонов
        baseline_summary = self._load_summary(self.baseline_dir)
        current_summary = self._load_summary(self.current_dir)
        
        if not baseline_summary or not current_summary:
            return {"error": "Не удалось загрузить summary"}
        
        # Создаём маппинг сценариев по имени
        baseline_scenarios = {s["scenario_name"]: s for s in baseline_summary.get("scenarios", [])}
        current_scenarios = {s["scenario_name"]: s for s in current_summary.get("scenarios", [])}
        
        # Сравниваем каждый сценарий
        all_names = set(baseline_scenarios.keys()) | set(current_scenarios.keys())
        
        for name in sorted(all_names):
            baseline = baseline_scenarios.get(name)
            current = current_scenarios.get(name)
            
            if not baseline:
                self.improvements.append({
                    "scenario": name,
                    "type": "new_scenario",
                    "message": "Новый сценарий (не было в baseline)"
                })
                continue
            
            if not current:
                self.regressions.append({
                    "scenario": name,
                    "type": "missing_scenario",
                    "message": "Сценарий пропущен в текущем прогоне"
                })
                continue
            
            # Сравниваем результаты
            self._compare_scenario(name, baseline, current)
        
        # Формируем отчёт
        report = self._generate_report(baseline_summary, current_summary)
        
        # Сохраняем отчёт
        report_file = self.current_dir / "comparison_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # Также в текстовом формате
        self._print_report(report)
        
        return report
    
    def _load_summary(self, run_dir: Path) -> Optional[dict]:
        """Загрузка summary.json."""
        summary_file = run_dir / "summary.json"
        if not summary_file.exists():
            print(f"❌ Не найден: {summary_file}")
            return None
        
        with open(summary_file, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _compare_scenario(self, name: str, baseline: dict, current: dict):
        """Сравнение одного сценария."""
        b_passed = baseline.get("passed", False)
        c_passed = current.get("passed", False)
        b_tours = baseline.get("final_tour_cards_count", 0)
        c_tours = current.get("final_tour_cards_count", 0)
        b_errors = baseline.get("errors_count", 0)
        c_errors = current.get("errors_count", 0)
        b_time = baseline.get("duration_seconds", 0)
        c_time = current.get("duration_seconds", 0)
        
        # Регрессия: было PASS, стало FAIL
        if b_passed and not c_passed:
            self.regressions.append({
                "scenario": name,
                "type": "pass_to_fail",
                "severity": "critical",
                "message": f"РЕГРЕССИЯ: было PASS → стало FAIL",
                "baseline_tours": b_tours,
                "current_tours": c_tours
            })
            return
        
        # Улучшение: было FAIL, стало PASS
        if not b_passed and c_passed:
            self.improvements.append({
                "scenario": name,
                "type": "fail_to_pass",
                "message": f"Улучшение: было FAIL → стало PASS",
                "baseline_tours": b_tours,
                "current_tours": c_tours
            })
            return
        
        # Оба PASS — проверяем количество туров
        if b_passed and c_passed:
            if c_tours < b_tours and b_tours > 0:
                # Меньше туров — потенциальная регрессия
                drop_pct = 100 * (b_tours - c_tours) / b_tours
                if drop_pct >= 50:
                    self.regressions.append({
                        "scenario": name,
                        "type": "tours_drop",
                        "severity": "warning",
                        "message": f"Падение туров: {b_tours} → {c_tours} ({drop_pct:.0f}%)",
                        "baseline_tours": b_tours,
                        "current_tours": c_tours
                    })
                    return
            
            if c_tours > b_tours:
                # Больше туров — улучшение
                self.improvements.append({
                    "scenario": name,
                    "type": "tours_increase",
                    "message": f"Больше туров: {b_tours} → {c_tours}",
                    "baseline_tours": b_tours,
                    "current_tours": c_tours
                })
                return
        
        # Новые ошибки
        if c_errors > b_errors:
            self.regressions.append({
                "scenario": name,
                "type": "new_errors",
                "severity": "warning",
                "message": f"Новые ошибки: {b_errors} → {c_errors}",
                "baseline_errors": b_errors,
                "current_errors": c_errors
            })
            return
        
        # Значительное замедление (>50%)
        if b_time > 0 and c_time > b_time * 1.5:
            self.regressions.append({
                "scenario": name,
                "type": "slowdown",
                "severity": "info",
                "message": f"Замедление: {b_time:.1f}s → {c_time:.1f}s",
                "baseline_time": b_time,
                "current_time": c_time
            })
            return
        
        # Без изменений
        self.unchanged.append({
            "scenario": name,
            "tours": c_tours,
            "passed": c_passed
        })
    
    def _generate_report(self, baseline_summary: dict, current_summary: dict) -> dict:
        """Генерация полного отчёта."""
        b_passed = baseline_summary.get("passed", 0)
        b_total = baseline_summary.get("total_scenarios", 0)
        c_passed = current_summary.get("passed", 0)
        c_total = current_summary.get("total_scenarios", 0)
        
        # Определяем статус
        critical_regressions = [r for r in self.regressions if r.get("severity") == "critical"]
        
        if critical_regressions:
            status = "REGRESSION_DETECTED"
            status_emoji = "🔴"
        elif self.regressions:
            status = "WARNINGS"
            status_emoji = "🟡"
        elif self.improvements:
            status = "IMPROVED"
            status_emoji = "🟢"
        else:
            status = "STABLE"
            status_emoji = "✅"
        
        return {
            "comparison_timestamp": datetime.now().isoformat(),
            "baseline_run": str(self.baseline_dir),
            "current_run": str(self.current_dir),
            "status": status,
            "status_emoji": status_emoji,
            "summary": {
                "baseline": {"passed": b_passed, "total": b_total, "pass_rate": f"{100*b_passed//b_total}%" if b_total else "N/A"},
                "current": {"passed": c_passed, "total": c_total, "pass_rate": f"{100*c_passed//c_total}%" if c_total else "N/A"},
            },
            "regressions_count": len(self.regressions),
            "critical_regressions": len(critical_regressions),
            "improvements_count": len(self.improvements),
            "unchanged_count": len(self.unchanged),
            "regressions": self.regressions,
            "improvements": self.improvements,
            "unchanged": self.unchanged
        }
    
    def _print_report(self, report: dict):
        """Вывод отчёта в консоль."""
        print(f"\n{'='*60}")
        print(f"{report['status_emoji']} РЕЗУЛЬТАТ СРАВНЕНИЯ: {report['status']}")
        print(f"{'='*60}")
        
        baseline = report["summary"]["baseline"]
        current = report["summary"]["current"]
        
        print(f"\n📊 Pass Rate:")
        print(f"   Baseline: {baseline['passed']}/{baseline['total']} ({baseline['pass_rate']})")
        print(f"   Current:  {current['passed']}/{current['total']} ({current['pass_rate']})")
        
        if report["regressions"]:
            print(f"\n🔴 РЕГРЕССИИ ({len(report['regressions'])}):")
            for r in report["regressions"]:
                severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(r.get("severity", "info"), "⚪")
                print(f"   {severity_icon} [{r['scenario']}] {r['message']}")
        
        if report["improvements"]:
            print(f"\n🟢 УЛУЧШЕНИЯ ({len(report['improvements'])}):")
            for i in report["improvements"]:
                print(f"   ✅ [{i['scenario']}] {i['message']}")
        
        print(f"\n📁 Полный отчёт: {self.current_dir}/comparison_report.json")


def find_latest_runs(output_base: str, count: int = 2) -> list[Path]:
    """Находит последние N прогонов."""
    output_dir = Path(output_base)
    if not output_dir.exists():
        return []
    
    runs = sorted(
        [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("run_")],
        key=lambda x: x.name,
        reverse=True
    )
    return runs[:count]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Runner с артефактами")
    parser.add_argument("--scenarios", type=str, help="JSON файл со сценариями")
    parser.add_argument("--output", type=str, default="test_results", help="Директория для артефактов")
    parser.add_argument("--url", type=str, default="http://localhost:8000", help="Base URL сервера")
    parser.add_argument("--example", action="store_true", help="Запустить примеры сценариев")
    parser.add_argument("--compare", action="store_true", help="Сравнить последние 2 прогона")
    parser.add_argument("--baseline", type=str, help="Путь к baseline прогону для сравнения")
    
    args = parser.parse_args()
    
    # Режим сравнения
    if args.compare:
        if args.baseline:
            # Сравнить с указанным baseline
            runs = find_latest_runs(args.output, 1)
            if not runs:
                print("❌ Нет прогонов для сравнения")
                sys.exit(1)
            comparator = RunComparator(Path(args.baseline), runs[0])
        else:
            # Сравнить последние 2 прогона
            runs = find_latest_runs(args.output, 2)
            if len(runs) < 2:
                print("❌ Нужно минимум 2 прогона для сравнения")
                sys.exit(1)
            comparator = RunComparator(runs[1], runs[0])  # [0] = latest, [1] = previous
        
        report = comparator.compare()
        sys.exit(0 if report.get("status") != "REGRESSION_DETECTED" else 1)
    
    # Режим запуска тестов
    runner = TestRunner(base_url=args.url, output_base=args.output)
    
    if args.example:
        scenarios = EXAMPLE_SCENARIOS
    elif args.scenarios:
        with open(args.scenarios, "r", encoding="utf-8") as f:
            scenarios = json.load(f)
    else:
        print("Укажите --scenarios FILE или --example или --compare")
        sys.exit(1)
    
    result = runner.run_all(scenarios)
    
    # Автоматическое сравнение с предыдущим прогоном
    runs = find_latest_runs(args.output, 2)
    if len(runs) >= 2:
        print("\n" + "="*60)
        print("🔄 Автоматическое сравнение с предыдущим прогоном...")
        comparator = RunComparator(runs[1], runs[0])
        comparator.compare()
