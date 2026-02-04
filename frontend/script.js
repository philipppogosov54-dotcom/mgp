/**
 * MGP Chat Widget - JavaScript
 * Сеть Магазинов Горящих Путевок
 * Production Version with Rich Tour Cards
 */

(function() {
    'use strict';

    // ============================================
    // CONFIGURATION
    // ============================================
    const CONFIG = {
        // API URL для локального тестирования
        apiUrl: (window.location.port === '5555' || window.location.protocol === 'file:')
            ? 'http://127.0.0.1:8080/api/v1/chat' 
            : window.location.origin + '/api/v1/chat',
        botName: 'MGP AI',
        typingDelay: 500,
        messageDelay: 100,
        maxVisibleCards: 3,  // Сколько карточек показывать изначально
        imageLoadTimeout: 5000
    };

    // ============================================
    // STATE
    // ============================================
    let conversationId = null;
    let isTyping = false;
    let allTourCards = [];  // Все полученные карточки
    let visibleCardsCount = 0;  // Сколько карточек сейчас отображается

    // ============================================
    // DOM ELEMENTS
    // ============================================
    const elements = {
        launcher: document.getElementById('chatLauncher'),
        widget: document.getElementById('chatWidget'),
        closeBtn: document.getElementById('chatClose'),
        messages: document.getElementById('chatMessages'),
        form: document.getElementById('chatForm'),
        input: document.getElementById('chatInput'),
        sendBtn: document.getElementById('chatSend'),
        typingIndicator: document.getElementById('typingIndicator')
    };

    // ============================================
    // UTILITIES
    // ============================================
    
    /**
     * Generate UUID v4
     */
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    /**
     * Format price with spaces (Russian style)
     */
    function formatPrice(price) {
        if (!price) return '—';
        return price.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    }

    /**
     * Format date from ISO string to Russian format
     */
    function formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('ru-RU', { 
            day: '2-digit', 
            month: '2-digit', 
            year: 'numeric' 
        });
    }

    /**
     * Format short date (DD.MM)
     */
    function formatShortDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('ru-RU', { 
            day: '2-digit', 
            month: '2-digit'
        });
    }

    /**
     * Generate star rating display
     */
    function generateStars(count) {
        return '★'.repeat(count || 0);
    }

    /**
     * Get nights word in Russian
     */
    function getNightsWord(nights) {
        const n = nights % 100;
        if (n >= 11 && n <= 19) return 'ночей';
        const lastDigit = n % 10;
        if (lastDigit === 1) return 'ночь';
        if (lastDigit >= 2 && lastDigit <= 4) return 'ночи';
        return 'ночей';
    }

    /**
     * Get meal description in Russian
     */
    function getMealDescription(foodType) {
        const descriptions = {
            'RO': 'Без питания',
            'BB': 'Только завтрак',
            'HB': 'Завтрак и ужин',
            'FB': 'Полный пансион',
            'AI': 'Всё включено',
            'UAI': 'Ультра всё включено'
        };
        return descriptions[foodType] || foodType || 'AI';
    }

    /**
     * Scroll messages to bottom
     */
    function scrollToBottom() {
        setTimeout(() => {
            elements.messages.scrollTop = elements.messages.scrollHeight;
        }, CONFIG.messageDelay);
    }

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Parse markdown-like formatting
     */
    function parseFormatting(text) {
        return text
            // Bold: **text** or __text__
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/__(.*?)__/g, '<strong>$1</strong>')
            // Italic: *text* or _text_
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/_(.*?)_/g, '<em>$1</em>')
            // Line breaks
            .replace(/\n/g, '<br>');
    }

    // ============================================
    // CHAT TOGGLE
    // ============================================
    
    function toggleChat() {
        const isOpen = elements.widget.classList.contains('open');
        
        if (isOpen) {
            closeChat();
        } else {
            openChat();
        }
    }

    function openChat() {
        elements.widget.classList.add('open');
        elements.launcher.classList.add('active');
        elements.input.focus();
        
        // Generate conversation ID if not exists
        if (!conversationId) {
            conversationId = generateUUID();
            console.log('New conversation:', conversationId);
        }
    }

    function closeChat() {
        elements.widget.classList.remove('open');
        elements.launcher.classList.remove('active');
    }

    // ============================================
    // MESSAGE RENDERING
    // ============================================

    /**
     * Create message bubble HTML
     */
    function createMessageHTML(role, content) {
        const isBot = role === 'bot' || role === 'assistant';
        const messageClass = isBot ? 'bot-message' : 'user-message';
        
        const avatarSvg = isBot 
            ? `<svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
               </svg>`
            : `<svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
               </svg>`;

        const formattedContent = parseFormatting(content);

        return `
            <div class="message ${messageClass}">
                <div class="message-avatar">${avatarSvg}</div>
                <div class="message-content">
                    <div class="message-bubble">${formattedContent}</div>
                </div>
            </div>
        `;
    }

    /**
     * Add message to chat
     */
    function addMessage(role, content) {
        const html = createMessageHTML(role, content);
        elements.messages.insertAdjacentHTML('beforeend', html);
        scrollToBottom();
    }

    /**
     * Create a single tour card HTML - PRODUCTION VERSION
     */
    function createTourCardHTML(tour, index) {
        // Extract data with fallbacks
        const hotelName = tour.hotel_name || 'Неизвестный отель';
        const stars = tour.hotel_stars || 4;
        const starsDisplay = tour.stars_display || generateStars(stars);
        const rating = tour.hotel_rating;
        const operator = tour.operator || '';
        
        // Location
        const country = tour.country || '';
        const resort = tour.resort || tour.region || '';
        const location = [country, resort].filter(Boolean).join(', ');
        
        // Dates
        const dateFrom = formatShortDate(tour.date_from);
        const dateTo = formatShortDate(tour.date_to);
        const nights = tour.nights || 7;
        const nightsWord = getNightsWord(nights);
        
        // Price
        const price = formatPrice(tour.price);
        const pricePerPerson = tour.price_per_person ? formatPrice(tour.price_per_person) : null;
        
        // Meal & Room
        const mealDesc = tour.meal_description || getMealDescription(tour.food_type);
        const foodCode = tour.food_type || 'AI';
        const roomType = tour.room_type || 'Standard';
        
        // Image URL with intelligent fallback
        const imageUrl = tour.image_url || tour.hotel_photo || getPlaceholderImage(country);
        
        // Links
        const hotelLink = tour.hotel_link || tour.original_link || '#';
        const tourId = tour.id || index;
        
        // Flight & departure info
        const departureCity = tour.departure_city || 'Москва';
        
        // FIX-FRONTEND: Определяем режим "только проживание"
        const isHotelOnly = tour.is_hotel_only || tour.flight_included === false;
        const priceLabel = isHotelOnly ? 'за проживание' : 'за тур';
        const bookBtnText = isHotelOnly ? '🏨 Забронировать' : '✈️ Оформить тур';

        return `
            <div class="tour-card ${isHotelOnly ? 'hotel-only' : ''}" data-tour-id="${escapeHtml(String(tourId))}">
                <div class="tour-card-image-container">
                    <img 
                        src="${escapeHtml(imageUrl)}" 
                        alt="${escapeHtml(hotelName)}" 
                        class="tour-card-image"
                        loading="lazy"
                        onerror="this.onerror=null; this.classList.add('placeholder'); this.parentElement.innerHTML='<div class=\\'tour-card-image placeholder\\'>🏨</div><div class=\\'tour-card-badge\\'>${starsDisplay}</div>';"
                    >
                    <div class="tour-card-badge">${starsDisplay}</div>
                    ${rating ? `<div class="tour-card-rating">${rating.toFixed(1)}</div>` : ''}
                </div>
                
                <div class="tour-card-body">
                    <div class="tour-card-hotel">${escapeHtml(hotelName)}</div>
                    <div class="tour-card-location">
                        <span class="icon">📍</span>
                        <span>${escapeHtml(location)}</span>
                    </div>
                    
                    <div class="tour-card-info">
                        ${!isHotelOnly ? `
                        <div class="tour-card-info-item highlight">
                            <span class="icon">✈️</span>
                            <div>
                                <div class="label">Перелёт</div>
                                <div class="value">Включён (${escapeHtml(departureCity)})</div>
                            </div>
                        </div>
                        ` : ''}
                        <div class="tour-card-info-item">
                            <span class="icon">📅</span>
                            <div>
                                <div class="label">Даты</div>
                                <div class="value">${dateFrom} – ${dateTo}</div>
                            </div>
                        </div>
                        <div class="tour-card-info-item">
                            <span class="icon">🌙</span>
                            <div>
                                <div class="label">Ночей</div>
                                <div class="value">${nights} ${nightsWord}</div>
                            </div>
                        </div>
                        <div class="tour-card-info-item">
                            <span class="icon">🍽️</span>
                            <div>
                                <div class="label">Питание</div>
                                <div class="value">${escapeHtml(mealDesc)}</div>
                            </div>
                        </div>
                        <div class="tour-card-info-item">
                            <span class="icon">🛏️</span>
                            <div>
                                <div class="label">Номер</div>
                                <div class="value room-badge">${escapeHtml(roomType)}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="tour-card-price-section">
                        <div class="tour-card-price">
                            <div class="tour-card-price-value">
                                ${price}<span class="currency">₽</span>
                            </div>
                            <div class="tour-card-price-label">${priceLabel}</div>
                        </div>
                        ${pricePerPerson ? `
                            <div class="tour-card-price-per-person">
                                <strong>${pricePerPerson} ₽</strong><br>за человека
                            </div>
                        ` : ''}
                    </div>
                    
                    <div class="tour-card-actions">
                        <a href="${escapeHtml(hotelLink)}" class="btn-book" target="_blank" rel="noopener">
                            ${bookBtnText}
                        </a>
                        <button class="btn-details" onclick="window.MGPChat.bookTour('${escapeHtml(hotelName)}')">
                            Забронировать через чат
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Get placeholder image based on country
     */
    function getPlaceholderImage(country) {
        const countryLower = (country || '').toLowerCase();
        const placeholders = {
            'турция': 'https://images.unsplash.com/photo-1524231757912-21f4fe3a7200?w=400&h=300&fit=crop',
            'египет': 'https://images.unsplash.com/photo-1539768942893-daf53e448371?w=400&h=300&fit=crop',
            'оаэ': 'https://images.unsplash.com/photo-1512453979798-5ea266f8880c?w=400&h=300&fit=crop',
            'таиланд': 'https://images.unsplash.com/photo-1552465011-b4e21bf6e79a?w=400&h=300&fit=crop',
            'мальдивы': 'https://images.unsplash.com/photo-1514282401047-d79a71a590e8?w=400&h=300&fit=crop',
            'кипр': 'https://images.unsplash.com/photo-1580996647286-a60cae5f8f80?w=400&h=300&fit=crop',
            'греция': 'https://images.unsplash.com/photo-1533105079780-92b9be482077?w=400&h=300&fit=crop'
        };
        
        for (const [key, url] of Object.entries(placeholders)) {
            if (countryLower.includes(key)) {
                return url;
            }
        }
        
        // Default beach image
        return 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=400&h=300&fit=crop';
    }

    /**
     * Create "Show More" button
     */
    function createShowMoreButton(remainingCount) {
        return `
            <button class="btn-show-more" onclick="window.MGPChat.showMoreCards()">
                <span class="icon">↓</span>
                Показать ещё ${remainingCount} ${remainingCount === 1 ? 'тур' : remainingCount < 5 ? 'тура' : 'туров'}
            </button>
        `;
    }

    /**
     * Render tour cards with horizontal carousel and navigation
     */
    function renderTourCards(cards, showAll = false) {
        if (!cards || cards.length === 0) return;

        // Store all cards for pagination
        allTourCards = cards;
        
        // Determine how many cards to show
        const cardsToShow = showAll ? cards : cards.slice(0, CONFIG.maxVisibleCards);
        visibleCardsCount = cardsToShow.length;
        
        const cardsHtml = cardsToShow.map((card, index) => createTourCardHTML(card, index)).join('');
        
        // Check if we need "Show More" button
        const remainingCount = cards.length - visibleCardsCount;
        const showMoreHtml = remainingCount > 0 ? createShowMoreButton(remainingCount) : '';
        
        // Navigation arrows for desktop (when more than 1 card)
        const navArrows = cardsToShow.length > 1 ? `
            <div class="tour-cards-nav-arrows">
                <button class="nav-prev" onclick="window.MGPChat.scrollCards(-1)" title="Предыдущий">‹</button>
                <button class="nav-next" onclick="window.MGPChat.scrollCards(1)" title="Следующий">›</button>
            </div>
        ` : '';
        
        // Navigation hint
        const navHint = `
            <div class="tour-cards-nav">
                <span class="tour-count">Найдено ${cards.length} ${cards.length === 1 ? 'тур' : cards.length < 5 ? 'тура' : 'туров'}</span>
                ${cardsToShow.length > 1 ? '<span class="swipe-hint">← листайте →</span>' : ''}
            </div>
        `;
        
        const containerHtml = `
            <div class="message bot-message">
                <div class="message-avatar">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
                    </svg>
                </div>
                <div class="message-content">
                    <div class="tour-cards-container" id="tourCardsContainer">
                        ${navArrows}
                        <div class="tour-cards-wrapper" id="tourCardsWrapper">
                            ${cardsHtml}
                        </div>
                        ${navHint}
                        ${showMoreHtml}
                    </div>
                </div>
            </div>
        `;

        elements.messages.insertAdjacentHTML('beforeend', containerHtml);
        scrollToBottom();
        
        // Preload images
        preloadCardImages(cardsToShow);
    }
    
    /**
     * Scroll cards in carousel by direction (-1 = prev, 1 = next)
     */
    function scrollCards(direction) {
        const wrapper = document.getElementById('tourCardsWrapper');
        if (!wrapper) return;
        
        const cardWidth = wrapper.querySelector('.tour-card')?.offsetWidth || 280;
        const gap = 12;
        const scrollAmount = (cardWidth + gap) * direction;
        
        wrapper.scrollBy({
            left: scrollAmount,
            behavior: 'smooth'
        });
    }

    /**
     * Show more tour cards
     */
    function showMoreCards() {
        const wrapper = document.getElementById('tourCardsWrapper');
        const container = document.getElementById('tourCardsContainer');
        
        if (!wrapper || !allTourCards.length) return;
        
        // Get remaining cards
        const remainingCards = allTourCards.slice(visibleCardsCount);
        
        // Add remaining cards
        remainingCards.forEach((card, index) => {
            const cardHtml = createTourCardHTML(card, visibleCardsCount + index);
            wrapper.insertAdjacentHTML('beforeend', cardHtml);
        });
        
        visibleCardsCount = allTourCards.length;
        
        // Remove "Show More" button
        const showMoreBtn = container.querySelector('.btn-show-more');
        if (showMoreBtn) {
            showMoreBtn.remove();
        }
        
        scrollToBottom();
        preloadCardImages(remainingCards);
    }

    /**
     * Preload card images for better UX
     */
    function preloadCardImages(cards) {
        cards.forEach(card => {
            const imageUrl = card.image_url || card.hotel_photo;
            if (imageUrl) {
                const img = new Image();
                img.src = imageUrl;
            }
        });
    }

    // ============================================
    // TYPING INDICATOR
    // ============================================

    function showTyping() {
        isTyping = true;
        elements.typingIndicator.classList.add('show');
        scrollToBottom();
    }

    function hideTyping() {
        isTyping = false;
        elements.typingIndicator.classList.remove('show');
    }

    // ============================================
    // API COMMUNICATION
    // ============================================

    /**
     * Send message to API
     */
    async function sendMessage(text) {
        if (!text.trim() || isTyping) return;

        // Add user message to chat
        addMessage('user', text);
        
        // Clear input
        elements.input.value = '';
        elements.sendBtn.disabled = true;

        // Show typing indicator
        showTyping();

        try {
            const response = await fetch(CONFIG.apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: text,
                    conversation_id: conversationId
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            // Update conversation ID from response
            if (data.conversation_id) {
                conversationId = data.conversation_id;
            }

            // Hide typing indicator
            hideTyping();

            // Add bot response
            if (data.reply) {
                addMessage('bot', data.reply);
            }

            // Render tour cards if present
            if (data.tour_cards && data.tour_cards.length > 0) {
                setTimeout(() => {
                    renderTourCards(data.tour_cards);
                }, CONFIG.typingDelay);
            }

        } catch (error) {
            console.error('Chat error:', error);
            hideTyping();
            addMessage('bot', 'Извините, произошла ошибка соединения. Пожалуйста, попробуйте позже или позвоните нам по телефону 8-800-XXX-XX-XX.');
        } finally {
            elements.sendBtn.disabled = false;
            elements.input.focus();
        }
    }

    /**
     * Book tour action - sends booking request through chat
     */
    function bookTour(hotelName) {
        const message = hotelName 
            ? `Хочу забронировать тур в ${hotelName}`
            : 'Хочу забронировать тур';
        sendMessage(message);
    }

    // ============================================
    // EVENT HANDLERS
    // ============================================

    function handleSubmit(e) {
        e.preventDefault();
        const text = elements.input.value.trim();
        if (text) {
            sendMessage(text);
        }
    }

    function handleKeyPress(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
        }
    }

    // ============================================
    // INITIALIZATION
    // ============================================

    function init() {
        // Check if all elements exist
        if (!elements.launcher || !elements.widget) {
            console.error('MGP Chat: Required elements not found');
            return;
        }

        // Event listeners
        elements.launcher.addEventListener('click', toggleChat);
        elements.closeBtn.addEventListener('click', closeChat);
        elements.form.addEventListener('submit', handleSubmit);
        elements.input.addEventListener('keypress', handleKeyPress);

        // Close on escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && elements.widget.classList.contains('open')) {
                closeChat();
            }
        });

        // Generate initial conversation ID
        conversationId = generateUUID();

        console.log('MGP Chat Widget initialized (Production Version)');
        console.log('Conversation ID:', conversationId);
    }

    // ============================================
    // PUBLIC API
    // ============================================
    
    window.MGPChat = {
        open: openChat,
        close: closeChat,
        toggle: toggleChat,
        send: sendMessage,
        bookTour: bookTour,
        showMoreCards: showMoreCards,
        scrollCards: scrollCards,
        getConversationId: () => conversationId
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
