"""
Админ-панель для мониторинга и анализа тестирования.

Endpoints:
- GET /admin/dashboard — HTML страница мониторинга
- GET /admin/sessions — список всех сессий с фильтрами
- GET /admin/session/{id} — детали сессии
- GET /admin/session/{id}/export — экспорт сессии в JSON
- POST /admin/notes — добавить заметку
- GET /admin/notes — список заметок
- PATCH /admin/notes/{id} — обновить заметку
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, Header, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])


# ==================== ADMIN AUTH ====================

def verify_admin_key(x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")) -> bool:
    """
    Проверка API ключа для доступа к админ-панели.
    
    Если ADMIN_API_KEY не задан — доступ открыт (для разработки).
    Если задан — требуется заголовок X-Admin-Key.
    """
    if not settings.ADMIN_API_KEY:
        # Ключ не настроен — разрешаем доступ (dev mode)
        return True
    
    if not x_admin_key:
        raise HTTPException(
            status_code=401, 
            detail="Missing X-Admin-Key header",
            headers={"WWW-Authenticate": "API-Key"}
        )
    
    if x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=403, 
            detail="Invalid admin API key"
        )
    
    return True


# ==================== PYDANTIC MODELS ====================

class TestNoteCreate(BaseModel):
    conversation_id: str
    content: str
    author: Optional[str] = None
    note_type: str = "comment"  # comment, bug, question, suggestion
    turn_id: Optional[int] = None
    priority: str = "normal"  # low, normal, high, critical
    tags: Optional[List[str]] = None


class TestNoteUpdate(BaseModel):
    content: Optional[str] = None
    status: Optional[str] = None  # open, in_progress, resolved, wont_fix
    resolution: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[List[str]] = None


# ==================== DASHBOARD ====================

@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(authorized: bool = Depends(verify_admin_key)):
    """
    HTML админ-панель для мониторинга тестирования.
    
    Требует X-Admin-Key заголовок если ADMIN_API_KEY задан.
    """
    if not settings.DATABASE_URL:
        return HTMLResponse("<h1>База данных не настроена</h1><p>Установите DATABASE_URL</p>")
    
    html_content = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MGP AI Assistant — Мониторинг</title>
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a24;
            --text-primary: #e4e4e7;
            --text-secondary: #a1a1aa;
            --accent: #8b5cf6;
            --accent-hover: #7c3aed;
            --success: #22c55e;
            --warning: #f59e0b;
            --error: #ef4444;
            --border: #27272a;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 24px;
        }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 32px;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border);
        }
        
        h1 {
            font-size: 28px;
            font-weight: 600;
            background: linear-gradient(135deg, var(--accent), #ec4899);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
            background: var(--bg-card);
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }
        
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }
        
        .stat-label {
            font-size: 13px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }
        
        .stat-value {
            font-size: 32px;
            font-weight: 600;
        }
        
        .stat-value.success { color: var(--success); }
        .stat-value.warning { color: var(--warning); }
        .stat-value.error { color: var(--error); }
        
        .section {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 16px;
            margin-bottom: 24px;
            overflow: hidden;
        }
        
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 24px;
            border-bottom: 1px solid var(--border);
        }
        
        .section-title {
            font-size: 18px;
            font-weight: 600;
        }
        
        .filters {
            display: flex;
            gap: 12px;
        }
        
        select, input[type="text"] {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 12px;
            color: var(--text-primary);
            font-size: 14px;
        }
        
        select:focus, input:focus {
            outline: none;
            border-color: var(--accent);
        }
        
        .sessions-list {
            max-height: 500px;
            overflow-y: auto;
        }
        
        .session-row {
            display: grid;
            grid-template-columns: 1fr 100px 120px 80px 150px 100px;
            gap: 16px;
            padding: 16px 24px;
            border-bottom: 1px solid var(--border);
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .session-row:hover {
            background: var(--bg-card);
        }
        
        .session-id {
            font-family: 'SF Mono', monospace;
            font-size: 13px;
            color: var(--accent);
        }
        
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .badge-active { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .badge-completed { background: rgba(139, 92, 246, 0.2); color: var(--accent); }
        .badge-abandoned { background: rgba(239, 68, 68, 0.2); color: var(--error); }
        
        .badge-bug { background: rgba(239, 68, 68, 0.2); color: var(--error); }
        .badge-comment { background: rgba(139, 92, 246, 0.2); color: var(--accent); }
        .badge-question { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        
        /* Session Detail Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            z-index: 1000;
            overflow-y: auto;
        }
        
        .modal.active { display: block; }
        
        .modal-content {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 16px;
            max-width: 900px;
            margin: 40px auto;
            overflow: hidden;
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 24px;
            border-bottom: 1px solid var(--border);
        }
        
        .modal-close {
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 24px;
            cursor: pointer;
        }
        
        .modal-body {
            padding: 24px;
        }
        
        .dialog-turn {
            margin-bottom: 24px;
            padding: 16px;
            background: var(--bg-card);
            border-radius: 12px;
        }
        
        .turn-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 12px;
            font-size: 13px;
            color: var(--text-secondary);
        }
        
        .turn-user {
            padding: 12px 16px;
            background: var(--accent);
            border-radius: 12px 12px 4px 12px;
            margin-bottom: 8px;
        }
        
        .turn-assistant {
            padding: 12px 16px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 4px 12px 12px 12px;
        }
        
        .turn-params {
            margin-top: 12px;
            padding: 12px;
            background: var(--bg-primary);
            border-radius: 8px;
            font-family: 'SF Mono', monospace;
            font-size: 12px;
            color: var(--text-secondary);
        }
        
        /* Notes */
        .notes-section {
            margin-top: 24px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
        }
        
        .note-form {
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
        }
        
        .note-form textarea {
            flex: 1;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px;
            color: var(--text-primary);
            resize: vertical;
            min-height: 60px;
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .btn-primary {
            background: var(--accent);
            color: white;
        }
        
        .btn-primary:hover {
            background: var(--accent-hover);
        }
        
        .note-item {
            padding: 12px;
            background: var(--bg-card);
            border-radius: 8px;
            margin-bottom: 8px;
        }
        
        .note-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 12px;
            color: var(--text-secondary);
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: var(--text-secondary);
        }
        
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-secondary);
        }
        
        .error-msg {
            padding: 12px;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 8px;
            color: var(--error);
            margin-bottom: 16px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔍 MGP AI Assistant — Мониторинг</h1>
            <div class="status-badge">
                <span class="status-dot"></span>
                <span id="db-status">Подключение...</span>
            </div>
        </header>
        
        <!-- Stats -->
        <div class="stats-grid" id="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Всего сессий</div>
                <div class="stat-value" id="stat-total">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Активных</div>
                <div class="stat-value success" id="stat-active">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Успешных поисков</div>
                <div class="stat-value" id="stat-searches">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Заметок/багов</div>
                <div class="stat-value warning" id="stat-notes">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Средн. сообщений</div>
                <div class="stat-value" id="stat-avg-msgs">-</div>
            </div>
        </div>
        
        <!-- Sessions List -->
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">📋 Сессии тестирования</h2>
                <div class="filters">
                    <select id="filter-status">
                        <option value="">Все статусы</option>
                        <option value="active">Активные</option>
                        <option value="completed">Завершённые</option>
                        <option value="abandoned">Брошенные</option>
                    </select>
                    <select id="filter-notes">
                        <option value="">Все</option>
                        <option value="with_notes">С заметками</option>
                        <option value="with_bugs">С багами</option>
                    </select>
                </div>
            </div>
            <div class="sessions-list" id="sessions-list">
                <div class="loading">Загрузка сессий...</div>
            </div>
        </div>
        
        <!-- Notes Section -->
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">📝 Последние заметки</h2>
            </div>
            <div id="notes-list" style="padding: 16px;">
                <div class="loading">Загрузка заметок...</div>
            </div>
        </div>
    </div>
    
    <!-- Session Detail Modal -->
    <div class="modal" id="session-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="modal-title">Сессия</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modal-body">
                <div class="loading">Загрузка...</div>
            </div>
        </div>
    </div>
    
    <script>
        const API_BASE = '/api/v1';
        
        // Load stats
        async function loadStats() {
            try {
                const resp = await fetch(`${API_BASE}/analytics/global`);
                const data = await resp.json();
                
                document.getElementById('stat-total').textContent = data.sessions?.total || 0;
                document.getElementById('stat-active').textContent = data.sessions?.active || 0;
                document.getElementById('stat-searches').textContent = data.search?.successful_sessions || 0;
                document.getElementById('stat-avg-msgs').textContent = (data.messages?.avg_per_session || 0).toFixed(1);
                document.getElementById('db-status').textContent = 'PostgreSQL подключен';
            } catch (e) {
                document.getElementById('db-status').textContent = 'Ошибка подключения';
                console.error(e);
            }
        }
        
        // Load sessions
        async function loadSessions() {
            const status = document.getElementById('filter-status').value;
            const notesFilter = document.getElementById('filter-notes').value;
            
            try {
                let url = `${API_BASE}/analytics/sessions/recent?limit=50`;
                if (status) url += `&status=${status}`;
                
                const resp = await fetch(url);
                const data = await resp.json();
                
                const list = document.getElementById('sessions-list');
                
                if (!data.sessions || data.sessions.length === 0) {
                    list.innerHTML = '<div class="empty-state">Нет сессий для отображения</div>';
                    return;
                }
                
                list.innerHTML = data.sessions.map(s => `
                    <div class="session-row" onclick="openSession('${s.conversation_id}')">
                        <div>
                            <div class="session-id">${s.conversation_id.substring(0, 8)}...</div>
                        </div>
                        <div>${s.message_count || 0} сообщ.</div>
                        <div>${s.tours_found || 0} туров</div>
                        <div>
                            <span class="badge badge-${s.status}">${s.status}</span>
                        </div>
                        <div style="color: var(--text-secondary); font-size: 13px;">
                            ${new Date(s.last_activity).toLocaleString('ru')}
                        </div>
                        <div>
                            ${s.has_booking_intent ? '🎯' : ''}
                            ${s.successful_search ? '✅' : ''}
                        </div>
                    </div>
                `).join('');
                
            } catch (e) {
                document.getElementById('sessions-list').innerHTML = 
                    '<div class="error-msg">Ошибка загрузки сессий</div>';
                console.error(e);
            }
        }
        
        // Load notes
        async function loadNotes() {
            try {
                const resp = await fetch(`${API_BASE}/admin/notes?limit=10`);
                const data = await resp.json();
                
                const list = document.getElementById('notes-list');
                document.getElementById('stat-notes').textContent = data.total || 0;
                
                if (!data.notes || data.notes.length === 0) {
                    list.innerHTML = '<div class="empty-state">Нет заметок</div>';
                    return;
                }
                
                list.innerHTML = data.notes.map(n => `
                    <div class="note-item">
                        <div class="note-header">
                            <span>
                                <span class="badge badge-${n.note_type}">${n.note_type}</span>
                                ${n.author || 'Аноним'} • 
                                <a href="#" onclick="openSession('${n.conversation_id}'); return false;" 
                                   style="color: var(--accent);">
                                    ${n.conversation_id.substring(0, 8)}...
                                </a>
                            </span>
                            <span>${new Date(n.created_at).toLocaleString('ru')}</span>
                        </div>
                        <div>${n.content}</div>
                    </div>
                `).join('');
                
            } catch (e) {
                document.getElementById('notes-list').innerHTML = 
                    '<div class="empty-state">Заметки недоступны</div>';
            }
        }
        
        // Open session modal
        async function openSession(convId) {
            const modal = document.getElementById('session-modal');
            const body = document.getElementById('modal-body');
            document.getElementById('modal-title').textContent = `Сессия: ${convId.substring(0, 12)}...`;
            
            modal.classList.add('active');
            body.innerHTML = '<div class="loading">Загрузка диалога...</div>';
            
            try {
                // Load dialogs
                const dialogResp = await fetch(`${API_BASE}/analytics/dialogs/${convId}`);
                const dialogData = await dialogResp.json();
                
                // Load notes for this session
                const notesResp = await fetch(`${API_BASE}/admin/notes?conversation_id=${convId}`);
                const notesData = await notesResp.json();
                
                let html = '';
                
                // Session info
                html += `
                    <div style="margin-bottom: 20px; padding: 16px; background: var(--bg-card); border-radius: 12px;">
                        <strong>ID:</strong> ${convId}<br>
                        <strong>Сообщений:</strong> ${dialogData.total_turns || 0}<br>
                        <button class="btn" onclick="exportSession('${convId}')" style="margin-top: 12px;">
                            📥 Экспорт JSON
                        </button>
                    </div>
                `;
                
                // Dialogs
                if (dialogData.dialogs && dialogData.dialogs.length > 0) {
                    dialogData.dialogs.forEach((d, i) => {
                        html += `
                            <div class="dialog-turn">
                                <div class="turn-header">
                                    <span>Ход #${i + 1}</span>
                                    <span>${d.response_time_ms?.toFixed(0) || '?'}ms</span>
                                </div>
                                <div class="turn-user">👤 ${escapeHtml(d.user_text)}</div>
                                <div class="turn-assistant">🤖 ${escapeHtml(d.assistant_text)}</div>
                                <div class="turn-params">
                                    <strong>Параметры:</strong> ${JSON.stringify(d.search_params || {}, null, 2)}<br>
                                    <strong>Недостающие:</strong> ${JSON.stringify(d.missing_params || [])}<br>
                                    <strong>Intent:</strong> ${d.intent || '-'} | 
                                    <strong>Stage:</strong> ${d.cascade_stage || '-'}
                                </div>
                            </div>
                        `;
                    });
                } else {
                    html += '<div class="empty-state">Нет сообщений</div>';
                }
                
                // Notes section
                html += `
                    <div class="notes-section">
                        <h3 style="margin-bottom: 16px;">📝 Заметки к сессии</h3>
                        <div class="note-form">
                            <textarea id="new-note-text" placeholder="Добавить заметку или баг..."></textarea>
                            <div>
                                <select id="new-note-type" style="margin-bottom: 8px; width: 100%;">
                                    <option value="comment">💬 Комментарий</option>
                                    <option value="bug">🐛 Баг</option>
                                    <option value="question">❓ Вопрос</option>
                                    <option value="suggestion">💡 Предложение</option>
                                </select>
                                <input type="text" id="new-note-author" placeholder="Ваше имя" 
                                       style="width: 100%; margin-bottom: 8px;">
                                <button class="btn btn-primary" onclick="addNote('${convId}')" 
                                        style="width: 100%;">Добавить</button>
                            </div>
                        </div>
                        <div id="session-notes">
                `;
                
                if (notesData.notes && notesData.notes.length > 0) {
                    notesData.notes.forEach(n => {
                        html += `
                            <div class="note-item">
                                <div class="note-header">
                                    <span>
                                        <span class="badge badge-${n.note_type}">${n.note_type}</span>
                                        ${n.author || 'Аноним'}
                                    </span>
                                    <span>${new Date(n.created_at).toLocaleString('ru')}</span>
                                </div>
                                <div>${escapeHtml(n.content)}</div>
                            </div>
                        `;
                    });
                } else {
                    html += '<div style="color: var(--text-secondary); text-align: center; padding: 20px;">Нет заметок</div>';
                }
                
                html += '</div></div>';
                
                body.innerHTML = html;
                
            } catch (e) {
                body.innerHTML = '<div class="error-msg">Ошибка загрузки данных</div>';
                console.error(e);
            }
        }
        
        // Close modal
        function closeModal() {
            document.getElementById('session-modal').classList.remove('active');
        }
        
        // Add note
        async function addNote(convId) {
            const content = document.getElementById('new-note-text').value.trim();
            const noteType = document.getElementById('new-note-type').value;
            const author = document.getElementById('new-note-author').value.trim();
            
            if (!content) {
                alert('Введите текст заметки');
                return;
            }
            
            try {
                const resp = await fetch(`${API_BASE}/admin/notes`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        conversation_id: convId,
                        content: content,
                        note_type: noteType,
                        author: author || null
                    })
                });
                
                if (resp.ok) {
                    // Reload modal and notes
                    openSession(convId);
                    loadNotes();
                } else {
                    alert('Ошибка сохранения');
                }
            } catch (e) {
                alert('Ошибка: ' + e.message);
            }
        }
        
        // Export session
        async function exportSession(convId) {
            try {
                const resp = await fetch(`${API_BASE}/admin/session/${convId}/export`);
                const data = await resp.json();
                
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `session_${convId}.json`;
                a.click();
            } catch (e) {
                alert('Ошибка экспорта');
            }
        }
        
        // Escape HTML
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Event listeners
        document.getElementById('filter-status').addEventListener('change', loadSessions);
        document.getElementById('filter-notes').addEventListener('change', loadSessions);
        
        // Close modal on outside click
        document.getElementById('session-modal').addEventListener('click', function(e) {
            if (e.target === this) closeModal();
        });
        
        // Initial load
        loadStats();
        loadSessions();
        loadNotes();
        
        // Auto-refresh every 30 seconds
        setInterval(() => {
            loadStats();
            loadSessions();
            loadNotes();
        }, 30000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


# ==================== NOTES API ====================

@router.post("/notes")
async def create_note(note: TestNoteCreate, authorized: bool = Depends(verify_admin_key)):
    """Добавить заметку к сессии. Требует X-Admin-Key."""
    if not settings.DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    
    from app.core.database import SessionLocal, TestNote
    
    db = SessionLocal()
    try:
        db_note = TestNote(
            conversation_id=note.conversation_id,
            content=note.content,
            author=note.author,
            note_type=note.note_type,
            turn_id=note.turn_id,
            priority=note.priority,
            tags=note.tags,
            created_at=datetime.utcnow()
        )
        db.add(db_note)
        db.commit()
        db.refresh(db_note)
        
        return {
            "id": db_note.id,
            "conversation_id": db_note.conversation_id,
            "note_type": db_note.note_type,
            "created_at": db_note.created_at.isoformat()
        }
    finally:
        db.close()


@router.get("/notes")
async def get_notes(
    conversation_id: Optional[str] = Query(None),
    note_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=200),
    authorized: bool = Depends(verify_admin_key)
):
    """Получить список заметок. Требует X-Admin-Key."""
    if not settings.DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    
    from app.core.database import SessionLocal, TestNote
    
    db = SessionLocal()
    try:
        query = db.query(TestNote)
        
        if conversation_id:
            query = query.filter(TestNote.conversation_id == conversation_id)
        if note_type:
            query = query.filter(TestNote.note_type == note_type)
        if status:
            query = query.filter(TestNote.status == status)
        
        notes = query.order_by(TestNote.created_at.desc()).limit(limit).all()
        
        return {
            "total": query.count(),
            "notes": [
                {
                    "id": n.id,
                    "conversation_id": n.conversation_id,
                    "author": n.author,
                    "note_type": n.note_type,
                    "content": n.content,
                    "turn_id": n.turn_id,
                    "priority": n.priority,
                    "status": n.status,
                    "tags": n.tags,
                    "created_at": n.created_at.isoformat() if n.created_at else None
                }
                for n in notes
            ]
        }
    finally:
        db.close()


@router.patch("/notes/{note_id}")
async def update_note(note_id: int, update: TestNoteUpdate, authorized: bool = Depends(verify_admin_key)):
    """Обновить заметку. Требует X-Admin-Key."""
    if not settings.DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    
    from app.core.database import SessionLocal, TestNote
    
    db = SessionLocal()
    try:
        note = db.query(TestNote).filter(TestNote.id == note_id).first()
        
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        
        if update.content is not None:
            note.content = update.content
        if update.status is not None:
            note.status = update.status
            if update.status == "resolved":
                note.resolved_at = datetime.utcnow()
        if update.resolution is not None:
            note.resolution = update.resolution
        if update.priority is not None:
            note.priority = update.priority
        if update.tags is not None:
            note.tags = update.tags
        
        note.updated_at = datetime.utcnow()
        db.commit()
        
        return {"status": "updated", "id": note_id}
    finally:
        db.close()


# ==================== SESSION EXPORT ====================

@router.get("/session/{conversation_id}/export")
async def export_session(conversation_id: str, authorized: bool = Depends(verify_admin_key)):
    """Экспорт полной информации о сессии в JSON. Требует X-Admin-Key."""
    if not settings.DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    
    from app.core.database import SessionLocal, DialogHistory, SessionAnalytics, TestNote, APICallLog
    
    db = SessionLocal()
    try:
        # Session info
        session = db.query(SessionAnalytics).filter_by(conversation_id=conversation_id).first()
        
        # Dialogs
        dialogs = db.query(DialogHistory).filter_by(
            conversation_id=conversation_id
        ).order_by(DialogHistory.turn_id).all()
        
        # Notes
        notes = db.query(TestNote).filter_by(
            conversation_id=conversation_id
        ).order_by(TestNote.created_at).all()
        
        # API calls
        api_calls = db.query(APICallLog).filter_by(
            conversation_id=conversation_id
        ).order_by(APICallLog.created_at).all()
        
        export_data = {
            "conversation_id": conversation_id,
            "exported_at": datetime.utcnow().isoformat(),
            "session": {
                "message_count": session.message_count if session else 0,
                "tour_searches": session.tour_searches if session else 0,
                "tours_found": session.tours_found if session else 0,
                "successful_search": session.successful_search if session else False,
                "has_booking_intent": session.has_booking_intent if session else False,
                "was_escalated": session.was_escalated if session else False,
                "status": session.status if session else "unknown",
                "collected_params": session.collected_params if session else [],
                "final_search_params": session.final_search_params if session else {},
                "started_at": session.started_at.isoformat() if session and session.started_at else None,
                "last_activity": session.last_activity.isoformat() if session and session.last_activity else None,
                "duration_seconds": session.duration_seconds if session else None
            },
            "dialogs": [
                {
                    "turn_id": d.turn_id,
                    "user_text": d.user_text,
                    "assistant_text": d.assistant_text,
                    "search_params": d.search_params,
                    "tour_offers": d.tour_offers,
                    "missing_params": d.missing_params,
                    "intent": d.intent,
                    "search_mode": d.search_mode,
                    "cascade_stage": d.cascade_stage,
                    "response_time_ms": d.response_time_ms,
                    "tours_found_count": d.tours_found_count,
                    "created_at": d.created_at.isoformat() if d.created_at else None
                }
                for d in dialogs
            ],
            "test_notes": [
                {
                    "id": n.id,
                    "author": n.author,
                    "note_type": n.note_type,
                    "content": n.content,
                    "turn_id": n.turn_id,
                    "priority": n.priority,
                    "status": n.status,
                    "resolution": n.resolution,
                    "tags": n.tags,
                    "created_at": n.created_at.isoformat() if n.created_at else None
                }
                for n in notes
            ],
            "api_calls": [
                {
                    "api_name": a.api_name,
                    "endpoint": a.endpoint,
                    "status_code": a.status_code,
                    "elapsed_ms": a.elapsed_ms,
                    "result_count": a.result_count,
                    "error": a.error,
                    "is_success": a.is_success,
                    "created_at": a.created_at.isoformat() if a.created_at else None
                }
                for a in api_calls
            ]
        }
        
        return JSONResponse(content=export_data)
    finally:
        db.close()
