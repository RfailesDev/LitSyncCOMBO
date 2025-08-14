/**
 * @file keep_active.js
 * @version 1.0
 * @description Модуль для поддержания активности вкладки AIStudio в фоновом режиме.
 * Использует requestAnimationFrame и легкие DOM-операции для обхода браузерного троттлинга.
 */

// Создаем глобальное пространство имен, если его еще нет
window.LitSyncModules = window.LitSyncModules || {};

(function(exports) {
    'use strict';

    const RAF_INTERVAL_MS = 1000; // Целевой интервал для requestAnimationFrame (1 секунда)
    const DOM_PING_INTERVAL_MS = 5000; // Интервал для легкого "пинания" DOM (5 секунд)

    let isActive = false;
    let rafId = null;
    let domPingIntervalId = null;
    let lastRafTime = 0;

    /**
     * Выполняет легкую DOM-операцию для поддержания активности.
     * Не изменяет DOM, только читает свойства.
     */
    function performLightDomPing() {
        try {
            // Чтение свойств, которые заставляют браузер пересчитывать стили/лейаут.
            // Это сигнализирует о том, что страница "жива" и требует внимания.
            // Используем document.body, чтобы не зависеть от конкретных элементов UI AIStudio.
            const bodyHeight = document.body.offsetHeight;
            const bodyWidth = document.body.offsetWidth;
            // console.log(`[LitSync KeepActive] DOM Ping: ${bodyHeight}x${bodyWidth}`);
        } catch (e) {
            console.warn('[LitSync KeepActive] Ошибка при DOM-пинге:', e);
        }
    }

    /**
     * Основной цикл requestAnimationFrame для поддержания активности.
     * @param {DOMHighResTimeStamp} timestamp - Время текущего кадра.
     */
    function rafLoop(timestamp) {
        if (!isActive) {
            rafId = null;
            return;
        }

        // Выполняем RAF с целевым интервалом
        if (timestamp - lastRafTime >= RAF_INTERVAL_MS) {
            // console.log(`[LitSync KeepActive] RAF Tick: ${timestamp.toFixed(2)}ms`);
            lastRafTime = timestamp;
            // Здесь можно добавить другие легкие операции, если необходимо
        }

        rafId = requestAnimationFrame(rafLoop);
    }

    /**
     * Запускает механизм поддержания активности.
     */
    function startKeepingActive() {
        if (isActive) {
            // console.log('[LitSync KeepActive] Уже активно.');
            return;
        }
        isActive = true;
        console.log('%c[LitSync KeepActive]%c Starting active mode...', 'color: #A076F9; font-weight: bold;', 'color: #34D399;');

        // Запускаем RAF loop
        if (!rafId) {
            lastRafTime = performance.now(); // Инициализируем время
            rafId = requestAnimationFrame(rafLoop);
        }

        // Запускаем периодический DOM-пинг
        if (!domPingIntervalId) {
            domPingIntervalId = setInterval(performLightDomPing, DOM_PING_INTERVAL_MS);
        }
    }

    /**
     * Останавливает механизм поддержания активности.
     */
    function stopKeepingActive() {
        if (!isActive) {
            // console.log('[LitSync KeepActive] Уже не активно.');
            return;
        }
        isActive = false;
        console.log('%c[LitSync KeepActive]%c Stopping active mode...', 'color: #A076F9; font-weight: bold;', 'color: #F87171;');

        if (rafId) {
            cancelAnimationFrame(rafId);
            rafId = null;
        }
        if (domPingIntervalId) {
            clearInterval(domPingIntervalId);
            domPingIntervalId = null;
        }
    }

    // Обработчик сообщений от background script
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.type === 'TOGGLE_KEEP_ACTIVE') {
            if (message.payload.enabled) {
                startKeepingActive();
            } else {
                stopKeepingActive();
            }
            sendResponse({ success: true });
            return true; // Keep the message channel open for async response
        }
    });

    // Экспортируем функции для возможного использования извне (хотя в данном случае только через сообщения)
    exports.keepActive = {
        start: startKeepingActive,
        stop: stopKeepingActive,
        get isActive() { return isActive; }
    };

    // При загрузке content script, проверяем начальное состояние из storage
    // Это важно, если пользователь уже включил опцию, а страница перезагрузилась.
    chrome.storage.sync.get('keepActiveEnabled', (data) => {
        if (data.keepActiveEnabled) {
            startKeepingActive();
        }
    });

})(window.LitSyncModules);