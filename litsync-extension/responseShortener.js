/**
 * @file responseShortener.js
 * @version 1.3 (Fix: Robust Stateful Shortening)
 * @description Модуль, инкапсулирующий логику сокращения ответов модели.
 * Использует надежный конечный автомат на data-атрибутах для корректной
 * работы с потоковыми данными.
 */

// Создаем глобальное пространство имен, если его еще нет
window.LitSyncModules = window.LitSyncModules || {};

// Оборачиваем всю логику в IIFE для инкапсуляции
(function(exports) {
    'use strict';

    // --- КОНСТАНТЫ МОДУЛЯ ---
    const START_TAG_ESCAPED = '&lt;files&gt;';
    const END_TAG_ESCAPED = '&lt;/files&gt;';
    const SHORTENED_CONTENT_CLASS = 'litsync-shortened-content';
    const SHORTEN_PROCESS_THROTTLE_MS = 100;
    const SHORTEN_FINALIZE_DEBOUNCE_MS = 250;

    // --- АТРИБУТЫ ДЛЯ УПРАВЛЕНИЯ СОСТОЯНИЕМ ---
    const STATE_ATTR = 'data-litsync-shortened'; // 'streaming', 'final'
    const PREFIX_ATTR = 'data-litsync-html-before'; // Хранит HTML до тега <files>

    // --- ВНУТРЕННЕЕ СОСТОЯНИЕ МОДУЛЯ ---
    const shortenObserverMap = new WeakMap();
    const debounceTimerMap = new WeakMap();

    /**
     * Утилита для "троттлинга" (прореживания) вызовов функции.
     * @param {Function} func - Функция для вызова.
     * @param {number} delay - Задержка в миллисекундах.
     * @returns {Function} - Обернутая функция.
     */
    function throttle(func, delay) {
        let timeoutId = null;
        let lastArgs = null;
        let lastThis = null;
        return function(...args) {
            lastArgs = args;
            lastThis = this;
            if (!timeoutId) {
                timeoutId = setTimeout(() => {
                    func.apply(lastThis, lastArgs);
                    timeoutId = null;
                }, delay);
            }
        };
    }

    /**
     * Создает HTML-элемент заглушки для сокращенного контента.
     * @returns {HTMLDivElement}
     */
    function createShortenedPlaceholder() {
        const placeholder = document.createElement('div');
        placeholder.className = SHORTENED_CONTENT_CLASS;
        // Используем простой текст, чтобы избежать проблем с парсингом HTML внутри innerHTML
        placeholder.textContent = 'Код файлов проекта сокращен для удобства.';

        const spinner = document.createElement('div');
        spinner.className = 'litsync-spinner';
        placeholder.prepend(spinner);

        return placeholder;
    }

    /**
     * Основная логика обработки, реализованная как конечный автомат.
     * @param {HTMLElement} contentArea - Элемент, содержащий HTML ответа модели.
     */
    function processShorteningForContainer(contentArea) {
        if (!contentArea) return;

        const currentState = contentArea.dataset.litsyncShortened;
        if (currentState === 'final') {
            return; // Работа завершена.
        }

        const fullHtml = contentArea.innerHTML;

        // --- СОСТОЯНИЕ: 'streaming' ---
        // Если мы уже в режиме сокращения, ищем только закрывающий тег.
        if (currentState === 'streaming') {
            if (fullHtml.includes(END_TAG_ESCAPED)) {
                const existingTimer = debounceTimerMap.get(contentArea);
                if (existingTimer) clearTimeout(existingTimer);

                const newTimer = setTimeout(() => {
                    const finalHtmlContent = contentArea.innerHTML;
                    const finalEndIndex = finalHtmlContent.indexOf(END_TAG_ESCAPED);
                    if (finalEndIndex === -1) return; // Тег исчез, выходим.

                    const container = contentArea.closest('.chat-turn-container.model.render');
                    // Важно: отключаем наблюдатель ПЕРЕД изменением DOM, чтобы избежать рекурсии.
                    if (container) cleanupShorteningForContainer(container);

                    const htmlBefore = contentArea.dataset.litsyncHtmlBefore || '';
                    const htmlAfter = finalHtmlContent.substring(finalEndIndex + END_TAG_ESCAPED.length);

                    contentArea.innerHTML = htmlBefore + createShortenedPlaceholder().outerHTML + htmlAfter;
                    contentArea.dataset.litsyncShortened = 'final';
                    contentArea.removeAttribute(PREFIX_ATTR); // Очистка
                    debounceTimerMap.delete(contentArea);

                }, SHORTEN_FINALIZE_DEBOUNCE_MS);

                debounceTimerMap.set(contentArea, newTimer);
            }
            return; // В режиме streaming больше ничего не делаем, ждем </files>.
        }

        // --- СОСТОЯНИЕ: initial (неопределенное) ---
        // Ищем открывающий тег, чтобы начать процесс.
        const startIndex = fullHtml.indexOf(START_TAG_ESCAPED);
        if (startIndex > -1) {
            // Тег найден. Начинаем сокращение.
            const htmlBefore = fullHtml.substring(0, startIndex);

            // 1. Сохраняем HTML до тега. Это КЛЮЧЕВОЙ шаг для надежности.
            contentArea.dataset.litsyncHtmlBefore = htmlBefore;

            // 2. Устанавливаем заглушку. Важно: мы отбрасываем всё ПОСЛЕ <files> на данный момент.
            // Это безопасно, т.к. следующий вызов MutationObserver принесет новый HTML.
            contentArea.innerHTML = htmlBefore + createShortenedPlaceholder().outerHTML;

            // 3. Переключаем состояние.
            contentArea.dataset.litsyncShortened = 'streaming';
        }
    }

    /**
     * Инициализирует наблюдение за DOM.
     * @param {HTMLElement} container - Родительский контейнер сообщения.
     * @param {HTMLElement} contentArea - Элемент с контентом для наблюдения.
     */
    function initializeShorteningForContainer(container, contentArea) {
        if (!container || !contentArea || container.dataset.litsyncShortenInit) {
            return;
        }
        container.dataset.litsyncShortenInit = 'true';

        const throttledProcess = throttle(() => {
            processShorteningForContainer(contentArea);
        }, SHORTEN_PROCESS_THROTTLE_MS);

        const observer = new MutationObserver(throttledProcess);
        observer.observe(contentArea, { childList: true, subtree: true, characterData: true });

        shortenObserverMap.set(container, observer);
        throttledProcess(); // Первоначальный запуск
    }

    /**
     * Прекращает наблюдение и очищает ресурсы.
     * @param {HTMLElement} container - Родительский контейнер сообщения.
     */
    function cleanupShorteningForContainer(container) {
        const observer = shortenObserverMap.get(container);
        if (observer) {
            observer.disconnect();
            shortenObserverMap.delete(container);
        }

        const contentArea = container.querySelector('ms-cmark-node');
        if (contentArea) {
            const timer = debounceTimerMap.get(contentArea);
            if (timer) {
                clearTimeout(timer);
                debounceTimerMap.delete(contentArea);
            }
        }
    }

    // Экспортируем публичные функции
    exports.responseShortener = {
        initializeShorteningForContainer,
        cleanupShorteningForContainer
    };

})(window.LitSyncModules);