/**
 * @file content.js
 * @version 27.0 (Fix: The "Wooden" Check)
 * @description Внедряет на страницу кнопки. Управляет модальными окнами.
 * - ИСПРАВЛЕНО: Система отслеживания теперь использует самый надежный ("деревянный")
 *   метод проверки: `textContent` кнопки "Run"/"Stop", что решает все проблемы с таймингами.
 * - УПРОЩЕНО: Логика машины состояний стала еще чище и надежнее.
 */

// --- ИМПОРТЫ (ЗАМЕНЕНЫ НА ДЕСТРУКТУРИЗАЦИЮ ИЗ ГЛОБАЛЬНОГО ОБЪЕКТА) ---
// Модули responseShortener и keep_active теперь доступны через window.LitSyncModules
const { initializeShorteningForContainer, cleanupShorteningForContainer } = window.LitSyncModules.responseShortener;

// --- КОНСТАНТЫ ---
const PROCESSED_MARKER = 'litsync-processed-v9';
const SYNC_BUTTON_CLASS = 'litsync-sync-button';
const CRAFT_BUTTON_CLASS = 'litsync-craft-button';
const MODAL_OVERLAY_CLASS = 'litsync-modal-overlay';
const SECONDARY_MODAL_OVERLAY_CLASS = 'litsync-secondary-modal-overlay';
const NOTIFICATION_TIMEOUT = 5000;
const SCAN_INTERVAL_MS = 250;
const ELEMENT_WAIT_TIMEOUT_MS = 5000;
const HIGHLIGHT_TIMEOUT_MS = 1000;
const FILTER_STATS_KEY = 'litsyncFilterStats';
const TOP_N_FREQUENT = 3;
// Новые константы для Response Watcher
const WATCHER_TICK_INTERVAL_MS = 300; // Увеличим частоту для большей точности
const RESPONSE_DEBOUNCE_MS = 1200; // Немного уменьшим, т.к. проверка стала надежнее

// --- ЦЕЛЕВЫЕ СЕЛЕКТОРЫ ---
const MESSAGE_CONTAINER_SELECTOR = '.chat-turn-container.model.render';
const MORE_OPTIONS_BUTTON_SELECTOR = 'ms-chat-turn-options button';
const COPY_MARKDOWN_BUTTON_SELECTOR = '.cdk-overlay-pane .copy-markdown-button';
const SNACKBAR_SELECTOR = '.mat-mdc-snack-bar-container';
const PROMPT_WRAPPER_SELECTOR = '.prompt-input-wrapper-container';
const PROMPT_TEXTAREA_SELECTOR = 'textarea[aria-label="Type something or tab to choose an example prompt"], textarea.gmat-body-medium[placeholder="Start typing a prompt"]';
const PROMPT_SEND_BUTTON_SELECTOR = '.run-button';
const CONTENT_AREA_SELECTOR = 'ms-cmark-node';
const STOPPABLE_RUN_BUTTON_CLASS = 'stoppable'; // Оставляем для справки, но не используем как триггер


// --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
let domScannerInterval = null;
let promptCrafterState = {};
let highlighterPromise = null;
let isShortenEnabled = false;

// Переменные для новой машины состояний
let watcherSystem = {
    intervalId: null,
    status: 'IDLE', // 'IDLE' | 'GENERATING'
    lastContentLength: -1,
    stableSince: null,
    soundSettings: null,
};


// --- SVG ИКОНКИ ---
const ICONS = {
    sync: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.6 6.41a.75.75 0 0 1 1.06 1.06l-2.5 2.5a.75.75 0 0 1-1.06 0l-2.5-2.5a.75.75 0 1 1 1.06-1.06L16 7.59V5a4 4 0 0 0-7.85-1.15.75.75 0 1 1-1.4-.4A5.5 5.5 0 0 1 20 5v2.59l1.19-1.18zM5.4 17.59a.75.75 0 0 1-1.06-1.06l2.5-2.5a.75.75 0 0 1 1.06 0l2.5 2.5a.75.75 0 1 1-1.06 1.06L8 16.41V19a4 4 0 0 0 7.85 1.15.75.75 0 1 1 1.4.4A5.5 5.5 0 0 1 4 19v-2.59L2.81 17.6z"/></svg>',
    craft: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6.1 6.1 9 1.6 4.5C.5 6.9.9 9.9 2.9 11.9c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.4-2.4c.4-.4.4-1 0-1.4z"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6.4 19L5 17.6l5.6-5.6L5 6.4L6.4 5l5.6 5.6L17.6 5L19 6.4L13.4 12l5.6 5.6l-1.4 1.4l-5.6-5.6L6.4 19z"/></svg>',
    dns: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 13h-4.26a3.001 3.001 0 0 1-5.48 0H5c-1.1 0-2 .9-2 2v4c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-4c0-1.1-.9-2-2-2zm-7 4c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-4-4h2.53a3.001 3.001 0 0 1 5.94 0H19v2h-2.12a3.001 3.001 0 0 1-4.76-1.54A2.992 2.992 0 0 1 8.12 15H5v-2zM5 3c-1.1 0-2 .9-2 2v4c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2H5zm7 6c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1z"/></svg>',
    arrow_forward_ios: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6.23 20.23L8 22l10-10L8 2L6.23 3.77L14.46 12z"/></svg>',
    progress_activity: '<svg viewBox="0 0 24 24" fill="currentColor" class="spinner"><path d="M12 2A10 10 0 1 0 12 22A10 10 0 0 0 12 2Zm0 18a8 8 0 0 1-8-8h2a6 6 0 0 0 6 6v2Z"/></svg>',
    check_circle: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>',
    error: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>',
    folder: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M10 4H4c-1.11 0-2 .9-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8c0-1.1-.9-2-2h-8l-2-2z"/></svg>`,
    file: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zM6 20V4h7v5h5v11H6z"/></svg>`,
    chevron_right: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>`,
    content_copy: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>`,
    check: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>`,
    open_in_full: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/></svg>`,
    settings: `<svg viewBox="0 0 24 24" fill="currentColor" width="128" height="128"><path d="M19.43 12.98c.04-.32.07-.64.07-.98s-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.39-.3-.61-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98l-.38-2.65C14.46 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42l-.38 2.65c-.61.25-1.17-.59-1.69-.98l-2.49-1c-.23-.09-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64l2.11 1.65c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65c-.19-.15-.24-.42-.12-.64l2 3.46c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69-.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49.42l.38-2.65c.61.25 1.17-.59-1.69.98l2.49-1c.23-.09.49 0 .61.22l2 3.46c.12.22.07.49-.12.64l-2.11-1.65zM12 15.5c-1.93 0-3.5-1.57-3.5-3.5s1.57-3.5 3.5-3.5 3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5z"></svg>`,
    library_add: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-1 9h-4v4h-2v-4H9V9h4V5h2v4h4v2z"/></svg>`,
    search: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>`,
    add_circle: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm5 11h-4v4h-2v-4H7v-2h4V7h2v4h4v2z"/></svg>`,
    article: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg>`,
    chip: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.73 4.17c-.39-.39-1.02-.39-1.41 0L14 6.54V4h-2v5h5V7h-2.54l2.37-2.37c.39-.38.39-1.02 0-1.46zM6.27 19.83c.39.39 1.02.39 1.41 0L10 17.46V20h2v-5H7v2h2.54l-2.37 2.37c-.39.38-.39 1.02 0 1.46z"/></svg>`,
    refresh: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>',
};

// --- МОДУЛЬ: Smart-аниматор модальных окон ---
const activeAnimations = new WeakMap();

async function animateModalResize(modalContent, updateCallback) {
    if (!modalContent) return;
    if (activeAnimations.has(modalContent)) {
        activeAnimations.get(modalContent).cancel();
    }
    const startingHeight = modalContent.offsetHeight;
    modalContent.style.height = `${startingHeight}px`;
    modalContent.style.overflow = 'hidden';
    modalContent.classList.add('is-animating');
    await Promise.resolve(updateCallback());
    const animationPromise = new Promise((resolve) => {
        requestAnimationFrame(() => {
            const modalBody = modalContent.querySelector('.litsync-modal-body');
            const header = modalContent.querySelector('.litsync-modal-header');
            const footer = modalContent.querySelector('.litsync-modal-footer');
            const newBodyHeight = modalBody.scrollHeight;
            const endingHeight = newBodyHeight + (header ? header.offsetHeight : 0) + (footer ? footer.offsetHeight : 0);
            if (Math.abs(endingHeight - startingHeight) < 2) {
                resolve();
                return;
            }
            modalContent.style.height = `${endingHeight}px`;
            const transitionendHandler = (event) => {
                if (event.propertyName === 'height') {
                    clearTimeout(fallbackTimeout);
                    resolve();
                }
            };
            const fallbackTimeout = setTimeout(resolve, 350);
            modalContent.addEventListener('transitionend', transitionendHandler, { once: true });
        });
    });
    const cancelAnimation = () => {
        modalContent.removeEventListener('transitionend', () => {});
    };
    activeAnimations.set(modalContent, { cancel: cancelAnimation });
    await animationPromise;
    modalContent.classList.remove('is-animating');
    modalContent.style.height = 'auto';
    modalContent.style.overflow = '';
    activeAnimations.delete(modalContent);
}


// --- КОНФИГУРАЦИЯ УНИВЕРСАЛЬНЫХ ФИЛЬТРОВ ---
const DEFAULT_FILTER_CONFIG = {
    all: {
        label: 'Все',
        isModifiable: false,
        exclude: ['min.js', 'min.css', 'lock', 'log', 'svg', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'ico', 'eot', 'ttf', 'woff', 'woff2', 'db', 'sqlite', 'sqlite3', 'DS_Store', 'pyc', 'pyd', 'egg-info', 'dist', 'build', 'venv', '.env', 'exe', 'dll', 'so', 'bin', 'dmg', 'iso']
    },
    backend: {
        label: 'Backend',
        isModifiable: true,
        requires: ['py'],
        extensions: ['py', 'json', 'txt', 'md', 'sh', 'yml', 'yaml', 'toml', 'ini', 'cfg', 'sql', 'dockerfile', 'conf']
    },
    frontend: {
        label: 'Frontend',
        isModifiable: true,
        requires: ['html', 'js', 'jsx', 'ts', 'tsx'],
        extensions: ['html', 'css', 'js', 'jsx', 'ts', 'tsx', 'scss', 'less', 'vue', 'svelte', 'json']
    }
};

async function getFilterConfig() {
    try {
        const {filterConfig: savedConfig} = await chrome.storage.local.get('filterConfig');
        const mergedConfig = JSON.parse(JSON.stringify(DEFAULT_FILTER_CONFIG));
        if (savedConfig) {
            for (const key in savedConfig) {
                if (mergedConfig[key] && mergedConfig[key].isModifiable) {
                    mergedConfig[key].extensions = savedConfig[key].extensions;
                }
            }
        }
        return mergedConfig;
    } catch (error) {
        console.error("LitSync: Ошибка загрузки конфигурации фильтров, используется дефолтная.", error);
        return DEFAULT_FILTER_CONFIG;
    }
}

async function saveFilterConfig(newConfig) {
    try {
        const configToSave = {};
        for (const key in newConfig) {
            if (newConfig[key].isModifiable) {
                configToSave[key] = {extensions: newConfig[key].extensions};
            }
        }
        await chrome.storage.local.set({filterConfig: configToSave});
        showNotification('Настройки фильтров сохранены.', 'success');
    } catch (error) {
        console.error("LitSync: Ошибка сохранения конфигурации фильтров.", error);
        showNotification('Не удалось сохранить настройки.', 'error');
    }
}

// --- КОММУНИКАЦИЯ С BACKGROUND.JS ---
function sendMessageToBackground(message) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(message, (response) => {
            if (chrome.runtime.lastError) {
                return reject(new Error(`Ошибка расширения: ${chrome.runtime.lastError.message}`));
            }
            if (response && !response.success) {
                return reject(new Error(response.error || 'Неизвестная ошибка от background скрипта'));
            }
            resolve(response);
        });
    });
}

// --- ЛОГИКА ИЗВЛЕЧЕНИЯ ТЕКСТА ---
function waitForElement(selector, timeout = ELEMENT_WAIT_TIMEOUT_MS) {
    return new Promise((resolve, reject) => {
        const element = document.querySelector(selector);
        if (element) return resolve(element);
        const observer = new MutationObserver(() => {
            const el = document.querySelector(selector);
            if (el) {
                observer.disconnect();
                clearTimeout(timer);
                resolve(el);
            }
        });
        const timer = setTimeout(() => {
            observer.disconnect();
            reject(new Error(`Таймаут: элемент "${selector}" не найден за ${timeout} мс.`));
        }, timeout);
        observer.observe(document.body, {childList: true, subtree: true});
    });
}

async function extractMarkdownViaUI(messageContainer) {
    let originalClipboardText = '';
    try {
        try {
            originalClipboardText = await navigator.clipboard.readText();
        } catch (err) {
            console.warn('LitSync: Не удалось прочитать исходный буфер обмена.', err.name);
        }
        const optionsButton = messageContainer.querySelector(MORE_OPTIONS_BUTTON_SELECTOR);
        if (!optionsButton) throw new Error('Не найдена кнопка "More options" (...)');
        optionsButton.click();
        const copyMarkdownButton = await waitForElement(COPY_MARKDOWN_BUTTON_SELECTOR);
        copyMarkdownButton.click();
        await waitForElement(SNACKBAR_SELECTOR);
        const markdownText = await navigator.clipboard.readText();
        return markdownText;
    } catch (error) {
        console.error('LitSync: Критическая ошибка в процессе извлечения Markdown:', error);
        throw error;
    } finally {
        if (typeof originalClipboardText === 'string') {
            await navigator.clipboard.writeText(originalClipboardText);
        }
        document.querySelector('.cdk-overlay-backdrop')?.click();
    }
}

// --- ОСНОВНАЯ ЛОГИКА РАСШИРЕНИЯ ---
function scanAndProcessMessages() {
    document.querySelectorAll(`${MESSAGE_CONTAINER_SELECTOR}:not(.${PROCESSED_MARKER})`).forEach(container => {
        container.classList.add(PROCESSED_MARKER);
        if (getComputedStyle(container).position === 'static') {
            container.style.position = 'relative';
        }
        const syncButton = document.createElement('button');
        syncButton.className = SYNC_BUTTON_CLASS;
        syncButton.type = 'button';
        syncButton.title = 'Отправить через LitSync';
        syncButton.innerHTML = ICONS.sync;
        syncButton.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            showClientSelectorForSync(container);
        });
        container.appendChild(syncButton);

        // ИСПОЛЬЗОВАНИЕ НОВОГО МОДУЛЯ
        if (isShortenEnabled) {
            const contentArea = container.querySelector(CONTENT_AREA_SELECTOR);
            if (contentArea) {
                initializeShorteningForContainer(container, contentArea);
            }
        }
    });
    document.querySelectorAll(`${PROMPT_WRAPPER_SELECTOR}:not(.${PROCESSED_MARKER})`).forEach(container => {
        container.classList.add(PROCESSED_MARKER);
        const craftButton = document.createElement('button');
        craftButton.className = CRAFT_BUTTON_CLASS;
        craftButton.type = 'button';
        craftButton.title = 'Создать промпт из файлов';
        craftButton.innerHTML = ICONS.craft;
        craftButton.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            openPromptCrafter();
        });
        const referenceNode = container.children[2];
        if (referenceNode) {
            container.insertBefore(craftButton, referenceNode);
        } else {
            container.appendChild(craftButton);
        }
    });
}

// --- ОБНОВЛЕННАЯ ЛОГИКА СИНХРОНИЗАЦИИ ---
async function showClientSelectorForSync(messageContainer) {
    const modal = createModal('Синхронизация: Шаг 1/2', {size: 'sm'});
    const listContainer = modal.querySelector('.litsync-modal-body');
    await loadAndRenderClients(listContainer, (client) => {
        showSyncPreview(client, messageContainer);
    });
}

async function showSyncPreview(client, messageContainer) {
    const modal = createModal(`Синхронизация: Шаг 2/2 (${client.name})`, {size: 'lg'});
    const body = modal.querySelector('.litsync-modal-body');

    await animateModalResize(modal, () => {
        renderLoading(body, 'Генерация предпросмотра...');
    });

    try {
        const markdownText = await extractMarkdownViaUI(messageContainer);
        const response = await sendMessageToBackground({
            type: 'PREVIEW_SYNC',
            payload: {text: markdownText, clientId: client.id}
        });
        const changes = response.data.changes;

        await animateModalResize(modal, () => {
            if (!changes || changes.length === 0) {
                renderError(body, 'Не найдено изменений для предпросмотра. Возможно, файлы идентичны.');
                return;
            }
            renderDiffUI(modal, changes, markdownText, client.id);
        });
    } catch (error) {
        await animateModalResize(modal, () => {
            renderError(body, `Ошибка генерации предпросмотра: ${error.message}`);
        });
    }
}

function renderDiffUI(modal, changes, originalMarkdown, clientId) {
    const body = modal.querySelector('.litsync-modal-body');
    body.innerHTML = `<div class="litsync-diff-view"></div>`;
    const container = body.querySelector('.litsync-diff-view');
    changes.forEach(fileChange => {
        const fileDiv = document.createElement('div');
        fileDiv.className = 'diff-file';
        let statusClass = `status-${fileChange.status}`;
        let statusText = fileChange.status.charAt(0).toUpperCase() + fileChange.status.slice(1);
        if (fileChange.status === 'added') statusText = 'Новый файл';
        fileDiv.innerHTML = ` <div class="diff-file-header"> <span class="diff-file-status ${statusClass}">${statusText}</span> <span class="diff-file-path">${fileChange.path}</span> </div> `;
        if (fileChange.hunks && fileChange.hunks.length > 0) {
            const hunksContainer = document.createElement('div');
            hunksContainer.className = 'diff-hunks-container';
            fileChange.hunks.forEach(hunk => {
                const table = document.createElement('table');
                table.className = 'diff-hunk';
                const tbody = document.createElement('tbody');
                hunk.lines.forEach(line => {
                    const tr = document.createElement('tr');
                    tr.className = `diff-line type-${line.type}`;
                    const escapedContent = line.content.replace(/</g, "&lt;").replace(/>/g, "&gt;");
                    tr.innerHTML = ` <td class="line-num old">${line.line_num_old || ''}</td> <td class="line-num new">${line.line_num_new || ''}</td> <td class="line-content">${escapedContent}</td> `;
                    tbody.appendChild(tr);
                });
                table.appendChild(tbody);
                hunksContainer.appendChild(table);
            });
            fileDiv.appendChild(hunksContainer);
        } else if (fileChange.status !== 'added') {
            fileDiv.innerHTML += `<div class="diff-no-changes">Нет видимых изменений.</div>`;
        }
        container.appendChild(fileDiv);
    });
    try {
        loadHighlighter().then(hljs => {
            container.querySelectorAll('td.line-content').forEach(el => {
                hljs.highlightElement(el);
            });
        });
    } catch (error) {
        console.error("LitSync: Не удалось применить подсветку синтаксиса.", error);
    }
    const footer = document.createElement('div');
    footer.className = 'litsync-modal-footer';
    const applyBtn = document.createElement('button');
    applyBtn.id = 'applyChangesBtn';
    applyBtn.className = 'litsync-btn litsync-btn-primary';
    applyBtn.textContent = 'Применить изменения';
    footer.appendChild(applyBtn);
    modal.appendChild(footer);
    applyBtn.addEventListener('click', async () => {
        applyBtn.disabled = true;
        applyBtn.innerHTML = `${ICONS.progress_activity} Применение...`;
        try {
            await sendMessageToBackground({type: 'SYNC_DATA', payload: {text: originalMarkdown, clientId: clientId}});
            showNotification(`Изменения успешно отправлены клиенту.`, 'success');
            closeModal();
        } catch (error) {
            showNotification(`Ошибка применения изменений: ${error.message}`, 'error');
            applyBtn.disabled = false;
            applyBtn.textContent = 'Применить изменения';
        }
    });
}

// --- ОБНОВЛЕННАЯ ЛОГИКА КОНСТРУКТОРА ПРОМПТОВ ---
function openPromptCrafter() {
    promptCrafterState = {
        step: 1,
        selectedClient: null,
        fileTree: [],
        selectedFiles: new Set(),
        filesWithContent: [],
        initialFrequentExtensions: [],
        selectedDocs: [],
    };
    renderPromptCrafterStep();
}

function renderPromptCrafterStep() {
    switch (promptCrafterState.step) {
        case 1:
            renderCrafterStep_SelectClient();
            break;
        case 2:
            renderCrafterStep_SelectFiles();
            break;
        case 3:
            renderCrafterStep_ComposePrompt();
            break;
    }
}

async function renderCrafterStep_SelectClient() {
    const modal = createModal('Конструктор промпта: Шаг 1/3', {size: 'sm'});
    const body = modal.querySelector('.litsync-modal-body');
    await loadAndRenderClients(body, (client) => {
        promptCrafterState.selectedClient = client;
        promptCrafterState.step = 2;
        renderPromptCrafterStep();
    });
}

// ИЗМЕНЕНО: Эта функция теперь использует скелетон
async function renderCrafterStep_SelectFiles() {
    const modal = createModal(`Конструктор промпта: Шаг 2/3 (${promptCrafterState.selectedClient.name})`, {size: 'lg'});
    const body = modal.querySelector('.litsync-modal-body');

    // 1. Показываем скелетон
    await animateModalResize(modal, () => {
        renderFileTreeSkeleton(body);
    });

    try {
        // 2. Загружаем данные
        const response = await sendMessageToBackground({
            type: 'GET_FILE_TREE',
            payload: {clientId: promptCrafterState.selectedClient.id}
        });
        promptCrafterState.fileTree = response.data.files || [];

        // 3. Плавно заменяем скелетон на реальный UI
        await animateModalResize(modal, () => {
            renderFileTreeUI(body);
        });
    } catch (error) {
        // 3. В случае ошибки, плавно заменяем скелетон на сообщение об ошибке
        await animateModalResize(modal, () => {
            renderError(body, `Не удалось загрузить файлы. (${error.message})`);
        });
    }
}

async function renderCrafterStep_ComposePrompt() {
    const modal = createModal('Конструктор промпта: Шаг 3/3', {size: 'md'});
    const body = modal.querySelector('.litsync-modal-body');

    await animateModalResize(modal, () => {
        renderLoading(body, 'Загрузка контента файлов...');
    });

    try {
        const selectedPaths = Array.from(promptCrafterState.selectedFiles);
        const contentResponse = await sendMessageToBackground({
            type: 'GET_FILE_CONTENT',
            payload: {clientId: promptCrafterState.selectedClient.id, paths: selectedPaths}
        });
        promptCrafterState.filesWithContent = contentResponse.data.files;
        await animateModalResize(modal, () => {
            renderComposeUI(body);
        });
    } catch (error) {
        await animateModalResize(modal, () => {
            renderError(body, `Ошибка при подготовке промпта: ${error.message}`);
        });
    }
}

// --- ХЕЛПЕРЫ ДЛЯ СТАТИСТИКИ ФИЛЬТРОВ ---
async function getFilterStats() {
    try {
        const {[FILTER_STATS_KEY]: stats} = await chrome.storage.local.get(FILTER_STATS_KEY);
        return stats || {};
    } catch (error) {
        console.error("LitSync: Не удалось загрузить статистику фильтров.", error);
        return {};
    }
}

async function incrementFilterStat(ext) {
    try {
        const stats = await getFilterStats();
        stats[ext] = (stats[ext] || 0) + 1;
        await chrome.storage.local.set({[FILTER_STATS_KEY]: stats});
    } catch (error) {
        console.error(`LitSync: Не удалось обновить статистику для .${ext}`, error);
    }
}

async function updateFilterStatsOnSessionEnd() {
    const selectedFiles = promptCrafterState.selectedFiles;
    const initialFrequent = promptCrafterState.initialFrequentExtensions;
    if (!selectedFiles || selectedFiles.size === 0 || !initialFrequent || initialFrequent.length === 0) {
        return;
    }
    const usedExtensions = new Set(Array.from(selectedFiles).map(path => path.split('.').pop()));
    const unusedFrequentExtensions = initialFrequent.filter(ext => !usedExtensions.has(ext));
    if (unusedFrequentExtensions.length > 0) {
        console.log('LitSync: Штраф для неиспользуемых фильтров:', unusedFrequentExtensions);
        const stats = await getFilterStats();
        let statsChanged = false;
        for (const ext of unusedFrequentExtensions) {
            if (stats[ext] && stats[ext] > 0) {
                stats[ext] -= 1;
                statsChanged = true;
            }
        }
        if (statsChanged) {
            await chrome.storage.local.set({[FILTER_STATS_KEY]: stats});
        }
    }
}

// --- UI-КОМПОНЕНТЫ И ХЕЛПЕРЫ ---

// НОВАЯ ФУНКЦИЯ: Генерирует HTML для скелетона
function renderFileTreeSkeleton(container) {
    const skeletonItem = (level = 0) => `
        <div class="skeleton-tree-item" style="--nest-level: ${level};">
            <div class="skeleton skeleton-icon"></div>
            <div class="skeleton skeleton-text"></div>
        </div>
    `;

    container.innerHTML = `
        <div class="litsync-file-selector">
            <div class="litsync-universal-filters">
                <div class="filter-group">
                    <div class="skeleton skeleton-filter-btn" style="width: 80px;"></div>
                    <div class="skeleton skeleton-filter-btn" style="width: 110px;"></div>
                    <div class="skeleton skeleton-filter-btn" style="width: 110px;"></div>
                </div>
                <div class="skeleton skeleton-settings-btn"></div>
            </div>
            <div class="litsync-file-filters">
                <div class="skeleton skeleton-ext-filter-btn"></div>
                <div class="skeleton skeleton-ext-filter-btn"></div>
                <div class="skeleton skeleton-ext-filter-btn"></div>
                <div class="skeleton skeleton-ext-filter-btn"></div>
                <div class="skeleton skeleton-ext-filter-btn"></div>
            </div>
            <div class="litsync-file-tree">
                ${skeletonItem(0)}
                <div class="skeleton-tree-item is-dir" style="--nest-level: 0;">
                    <div class="skeleton skeleton-icon"></div>
                    <div class="skeleton skeleton-text" style="width: 40%;"></div>
                </div>
                <div class="skeleton-tree-level" style="padding-left: 24px;">
                    ${skeletonItem(1)}
                    ${skeletonItem(1)}
                    <div class="skeleton-tree-item is-dir" style="--nest-level: 1;">
                        <div class="skeleton skeleton-icon"></div>
                        <div class="skeleton skeleton-text" style="width: 50%;"></div>
                    </div>
                     <div class="skeleton-tree-level" style="padding-left: 24px;">
                        ${skeletonItem(2)}
                    </div>
                </div>
                ${skeletonItem(0)}
                ${skeletonItem(0)}
            </div>
        </div>
    `;
}


function createModal(title, options = {}) {
    closeModal(options.isSecondary ? SECONDARY_MODAL_OVERLAY_CLASS : MODAL_OVERLAY_CLASS);
    const {size = 'md', isSecondary = false} = options;
    const overlay = document.createElement('div');
    overlay.className = isSecondary ? SECONDARY_MODAL_OVERLAY_CLASS : MODAL_OVERLAY_CLASS;
    overlay.innerHTML = ` <div class="litsync-modal-content size-${size} ${isSecondary ? 'is-secondary' : ''}"> <div class="litsync-modal-header"> <h2>${title}</h2> <button class="litsync-modal-close-btn" title="Закрыть">${ICONS.close}</button> </div> <div class="litsync-modal-body"></div> </div> `;
    document.body.appendChild(overlay);

    const modalContent = overlay.querySelector('.litsync-modal-content');

    setTimeout(() => overlay.classList.add('visible'), 10);
    const closeBtn = overlay.querySelector('.litsync-modal-close-btn');
    const closeFunc = () => {
        overlay.classList.remove('visible');
        overlay.addEventListener('transitionend', () => overlay.remove(), {once: true});
    };
    if (!isSecondary) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeFunc();
        });
    }
    closeBtn.addEventListener('click', closeFunc);
    return modalContent;
}

function closeModal(selector = `.${MODAL_OVERLAY_CLASS}, .${SECONDARY_MODAL_OVERLAY_CLASS}`) {
    if (selector.includes(MODAL_OVERLAY_CLASS)) {
        const fileSelector = document.querySelector('.litsync-file-selector');
        if (fileSelector) {
            updateFilterStatsOnSessionEnd();
        }
    }
    document.querySelectorAll(selector).forEach(el => {
        el.classList.remove('visible');
        el.addEventListener('transitionend', () => el.remove(), {once: true});
    });
}

function renderLoading(container, text) {
    container.innerHTML = `<div class="litsync-list-state">${ICONS.progress_activity}<p>${text}</p></div>`;
}

function renderError(container, text) {
    container.innerHTML = `<div class="litsync-list-state">${ICONS.error}<p>${text}</p></div>`;
}

function renderClientListSkeleton(container) {
    const skeletonItem = `
        <div class="litsync-client-item is-loading">
            <div class="skeleton skeleton-icon"></div>
            <div class="skeleton skeleton-text"></div>
        </div>
    `;
    container.innerHTML = `
        <div class="litsync-list-header">
            <h3>Выберите клиента</h3>
            <button class="litsync-refresh-btn" disabled title="Обновление...">
                ${ICONS.progress_activity}
            </button>
        </div>
        <div class="litsync-client-list">
            ${skeletonItem.repeat(3)}
        </div>
    `;
    container.querySelector('.litsync-refresh-btn svg').classList.add('spinner');
}

function renderClientList(container, clients, onSelect, onRefresh) {
    container.innerHTML = `
        <div class="litsync-list-header">
            <h3>Выберите клиента</h3>
            <button class="litsync-refresh-btn" title="Обновить список">
                ${ICONS.refresh}
            </button>
        </div>
        <div class="litsync-client-list"></div>
    `;
    const list = container.querySelector('.litsync-client-list');
    clients.forEach(client => {
        const item = document.createElement('div');
        item.className = 'litsync-client-item';
        item.innerHTML = `<span class="client-icon">${ICONS.dns}</span><span class="client-name">${client.name}</span><span class="action-indicator">${ICONS.arrow_forward_ios}</span>`;
        item.addEventListener('click', () => onSelect(client));
        list.appendChild(item);
    });
    container.querySelector('.litsync-refresh-btn').addEventListener('click', onRefresh);
}

async function loadAndRenderClients(container, onSelectCallback) {
    const modalContent = container.closest('.litsync-modal-content');
    const refreshCallback = () => loadAndRenderClients(container, onSelectCallback);

    await animateModalResize(modalContent, () => {
        renderClientListSkeleton(container);
    });

    try {
        const response = await sendMessageToBackground({type: 'GET_CLIENTS'});
        const clients = response.data;

        await animateModalResize(modalContent, () => {
            if (!clients || clients.length === 0) {
                container.innerHTML = `
                    <div class="litsync-list-header">
                        <h3>Выберите клиента</h3>
                        <button class="litsync-refresh-btn" title="Обновить список">${ICONS.refresh}</button>
                    </div>
                    <div class="litsync-client-list">
                       <div class="litsync-list-state">${ICONS.error}<p>Активные клиенты не найдены.</p></div>
                    </div>`;
                container.querySelector('.litsync-refresh-btn').addEventListener('click', refreshCallback);
                return;
            }
            renderClientList(container, clients, onSelectCallback, refreshCallback);
        });
    } catch (error) {
        await animateModalResize(modalContent, () => {
            container.innerHTML = `
                <div class="litsync-list-header">
                    <h3>Выберите клиента</h3>
                    <button class="litsync-refresh-btn" title="Обновить список">${ICONS.refresh}</button>
                </div>
                <div class="litsync-client-list">
                   <div class="litsync-list-state">${ICONS.error}<p>Не удалось загрузить клиентов. (${error.message})</p></div>
                </div>`;
            container.querySelector('.litsync-refresh-btn').addEventListener('click', refreshCallback);
        });
    }
}

function renderFileTreeUI(container) {
    const filePaths = promptCrafterState.fileTree;
    const allExtensionsInProject = [...new Set(filePaths.map(p => p.split('.').pop()).filter(Boolean))];
    getFilterConfig().then(config => {
        getFilterStats().then(stats => {
            const frequentExtensions = Object.entries(stats).sort(([, a], [, b]) => b - a).slice(0, TOP_N_FREQUENT).map(([ext]) => ext);
            promptCrafterState.initialFrequentExtensions = frequentExtensions;
            let universalFiltersHTML = '';
            for (const key in config) {
                const filter = config[key];
                const requirementsMet = !filter.requires || filter.requires.some(req => allExtensionsInProject.includes(req));
                if (requirementsMet) {
                    universalFiltersHTML += `<button class="litsync-btn litsync-btn-secondary universal-filter-btn" data-filter-key="${key}">${filter.label}</button>`;
                }
            }
            const extensions = allExtensionsInProject.filter(ext => ext.length < 5).sort();
            container.innerHTML = ` <div class="litsync-file-selector"> <div class="litsync-universal-filters"> <div class="filter-group">${universalFiltersHTML}</div> <button class="settings-btn" title="Настроить фильтры">${ICONS.settings}</button> </div> <div class="litsync-file-filters"> ${extensions.map(ext => {
                const isFrequent = frequentExtensions.includes(ext);
                const frequentClass = isFrequent ? 'litsync-frequent-filter' : '';
                return `<button class="filter-btn ${frequentClass}" data-ext="${ext}">.${ext}</button>`;
            }).join('')} </div> <div class="litsync-file-tree"></div> <div class="litsync-modal-footer"> <button id="crafterNextBtn" class="litsync-btn litsync-btn-primary" disabled>Далее</button> </div> </div> `;
            const treeContainer = container.querySelector('.litsync-file-tree');
            treeContainer.appendChild(renderTree(buildTree(filePaths)));
            const nextBtn = container.querySelector('#crafterNextBtn');
            const updateNextBtn = () => {
                const selectedCount = promptCrafterState.selectedFiles.size;
                nextBtn.disabled = selectedCount === 0;
                nextBtn.textContent = selectedCount > 0 ? `Далее (${selectedCount})` : 'Далее';
            };
            const fileSelector = container.querySelector('.litsync-file-selector');
            fileSelector.addEventListener('click', async (e) => {
                const target = e.target;
                const universalFilterBtn = target.closest('.universal-filter-btn');
                const filterBtn = target.closest('.filter-btn');
                const settingsBtn = target.closest('.settings-btn');
                const dirItem = target.closest('.file-tree-item.is-dir');
                if (universalFilterBtn) {
                    const key = universalFilterBtn.dataset.filterKey;
                    const currentConfig = await getFilterConfig();
                    handleUniversalFilterClick(container, key, currentConfig[key]);
                    return;
                }
                if (filterBtn) {
                    await handleExtensionFilterClick(container, filterBtn.dataset.ext);
                    return;
                }
                if (settingsBtn) {
                    openFilterSettingsModal();
                    return;
                }
                if (dirItem && !target.closest('.custom-checkbox')) {
                    dirItem.classList.toggle('is-open');
                }
            });
            fileSelector.addEventListener('change', (e) => {
                const checkbox = e.target;
                if (checkbox.type !== 'checkbox') return;
                const isChecked = checkbox.checked;
                const listItem = checkbox.closest('li.file-tree-item');
                const childrenCheckboxes = Array.from(listItem.querySelectorAll('input[type="checkbox"]'));
                childrenCheckboxes.forEach(child => {
                    if (child.checked !== isChecked) {
                        child.checked = isChecked;
                    }
                    if (child.dataset.path) {
                        if (isChecked) {
                            promptCrafterState.selectedFiles.add(child.dataset.path);
                        } else {
                            promptCrafterState.selectedFiles.delete(child.dataset.path);
                        }
                    }
                });
                updateNextBtn();
            });
            nextBtn.addEventListener('click', async () => {
                if (promptCrafterState.selectedFiles.size > 0) {
                    await updateFilterStatsOnSessionEnd();
                    promptCrafterState.step = 3;
                    renderPromptCrafterStep();
                }
            });
        });
    });
}

function handleUniversalFilterClick(container, key, config) {
    const allFileCheckboxes = Array.from(container.querySelectorAll('.file-tree-item.is-file input[type="checkbox"]'));
    let targetCheckboxes = [];
    if (key === 'all') {
        targetCheckboxes = allFileCheckboxes.filter(cb => {
            const path = cb.dataset.path;
            const fileName = path.split('/').pop();
            return !config.exclude.some(ex => fileName.endsWith(ex) || fileName.toLowerCase().endsWith(`.${ex}`));
        });
    } else {
        targetCheckboxes = allFileCheckboxes.filter(cb => config.extensions.includes(cb.closest('.is-file').dataset.ext));
    }
    if (targetCheckboxes.length > 0) {
        const isAnyUnchecked = targetCheckboxes.some(cb => !cb.checked);
        targetCheckboxes.forEach(cb => {
            if (cb.checked !== isAnyUnchecked) {
                cb.checked = isAnyUnchecked;
                cb.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
        targetCheckboxes.forEach(cb => {
            const item = cb.closest('.file-tree-item');
            item.classList.remove('highlight-flash');
            void item.offsetWidth;
            item.classList.add('highlight-flash');
            setTimeout(() => item.classList.remove('highlight-flash'), HIGHLIGHT_TIMEOUT_MS);
        });
    }
}

async function handleExtensionFilterClick(container, ext) {
    await incrementFilterStat(ext);
    const fileItems = container.querySelectorAll(`.file-tree-item.is-file[data-ext="${ext}"]`);
    const checkboxes = Array.from(fileItems).map(item => item.querySelector('input[type="checkbox"]'));
    const isAnyUnchecked = checkboxes.some(cb => !cb.checked);
    checkboxes.forEach(cb => {
        if (cb.checked !== isAnyUnchecked) {
            cb.checked = isAnyUnchecked;
            cb.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });
    fileItems.forEach(item => {
        item.classList.remove('highlight-flash');
        void item.offsetWidth;
        item.classList.add('highlight-flash');
        setTimeout(() => item.classList.remove('highlight-flash'), HIGHLIGHT_TIMEOUT_MS);
    });
}

async function openFilterSettingsModal() {
    const modal = createModal('Настройка универсальных фильтров', {size: 'md', isSecondary: true});
    const body = modal.querySelector('.litsync-modal-body');
    await animateModalResize(modal, () => renderLoading(body, 'Загрузка...'));
    const config = await getFilterConfig();
    await animateModalResize(modal, () => renderFilterSettingsUI(modal, config));
}

function renderFilterSettingsUI(modal, config) {
    const body = modal.querySelector('.litsync-modal-body');
    let editableFiltersHTML = '';
    for (const key in config) {
        const filter = config[key];
        if (filter.isModifiable) {
            editableFiltersHTML += ` <div class="settings-filter-group" data-filter-key="${key}"> <label>${filter.label}</label> <div class="tag-input-container"> ${filter.extensions.map(ext => `<span class="tag">${ext}<button class="remove-tag">&times;</button></span>`).join('')} <input type="text" class="tag-input" placeholder="Добавить расширение..."> </div> </div> `;
        }
    }
    body.innerHTML = `<div class="litsync-settings-view">${editableFiltersHTML}</div>`;
    body.querySelectorAll('.settings-filter-group').forEach(group => {
        const input = group.querySelector('.tag-input');
        const container = group.querySelector('.tag-input-container');
        container.addEventListener('click', e => {
            if (e.target.classList.contains('remove-tag')) {
                e.target.parentElement.remove();
            }
        });
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ',' || e.key === ' ') {
                e.preventDefault();
                const value = input.value.trim().replace(/^\./, '');
                if (value) {
                    const newTag = document.createElement('span');
                    newTag.className = 'tag';
                    newTag.innerHTML = `${value}<button class="remove-tag">&times;</button>`;
                    container.insertBefore(newTag, input);
                    input.value = '';
                }
            }
        });
    });
    const footer = document.createElement('div');
    footer.className = 'litsync-modal-footer';
    const saveBtn = document.createElement('button');
    saveBtn.className = 'litsync-btn litsync-btn-primary';
    saveBtn.textContent = 'Сохранить и закрыть';
    footer.appendChild(saveBtn);
    modal.appendChild(footer);
    saveBtn.addEventListener('click', async () => {
        const newConfig = JSON.parse(JSON.stringify(config));
        body.querySelectorAll('.settings-filter-group').forEach(group => {
            const key = group.dataset.filterKey;
            const extensions = Array.from(group.querySelectorAll('.tag')).map(tag => tag.firstChild.textContent);
            if (newConfig[key]) {
                newConfig[key].extensions = extensions;
            }
        });
        await saveFilterConfig(newConfig);
        closeModal(`.${SECONDARY_MODAL_OVERLAY_CLASS}`);
        const primaryModal = document.querySelector(`.${MODAL_OVERLAY_CLASS} .litsync-modal-content`);
        if (primaryModal) {
            const body = primaryModal.querySelector('.litsync-modal-body');
            await animateModalResize(primaryModal, () => renderFileTreeUI(body));
        }
    });
}

function buildTree(paths) {
    const tree = {};
    paths.forEach(path => {
        path.split('/').reduce((r, name) => r[name] || (r[name] = {}), tree);
    });
    return tree;
}

function renderTree(node, path = '', level = 0) {
    const ul = document.createElement('ul');
    ul.className = 'file-tree-level';
    const sortedKeys = Object.keys(node).sort((a, b) => {
        const isADir = Object.keys(node[a]).length > 0;
        const isBDir = Object.keys(node[b]).length > 0;
        if (isADir && !isBDir) return -1;
        if (!isADir && isBDir) return 1;
        return a.localeCompare(b);
    });
    sortedKeys.forEach(key => {
        const li = document.createElement('li');
        const currentPath = path ? `${path}/${key}` : key;
        const isDir = Object.keys(node[key]).length > 0;
        const ext = isDir ? '' : key.split('.').pop();
        const idSuffix = currentPath.replace(/[^a-zA-Z0-9]/g, '-');
        li.className = `file-tree-item ${isDir ? 'is-dir' : 'is-file'}`;
        li.style.setProperty('--nest-level', level);
        if (!isDir) {
            li.dataset.ext = ext;
        }
        const icon = isDir ? ICONS.chevron_right : ICONS.file;
        const labelText = key;
        const labelTag = isDir ? 'div' : 'label';
        li.innerHTML = ` <${labelTag} class="item-label" ${!isDir ? `for="cb-${idSuffix}"` : ''}> <label class="custom-checkbox" for="cb-${idSuffix}"> <input type="checkbox" id="cb-${idSuffix}" data-path="${currentPath}"> <span class="checkmark"></span> </label> <span class="item-icon">${icon}</span> <span class="item-text">${labelText}</span> </${labelTag}> `;
        if (isDir) {
            li.appendChild(renderTree(node[key], currentPath, level + 1));
        }
        ul.appendChild(li);
    });
    return ul;
}

// --- НОВЫЕ И ОБНОВЛЕННЫЕ ФУНКЦИИ ДЛЯ CONTEXT7 ---

function formatTokens(tokens) {
    if (tokens >= 1000) {
        return (tokens / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
    }
    return tokens.toString();
}

function renderComposeUI(container) {
    container.innerHTML = `
    <div class="litsync-compose-view">
        <div class="context7-section">
            <div class="context7-header">
                <label>Дополнительный контекст</label>
                <button id="addContextBtn" class="litsync-btn litsync-btn-secondary">${ICONS.library_add} Добавить документацию</button>
            </div>
            <div id="context7-pills-container" class="context7-pills-container">
            </div>
        </div>

        <div class="compose-field">
            <label for="promptTask">1. Ваша задача (что нужно сделать?)</label>
            <div class="compose-field-wrapper">
                <textarea id="promptTask" placeholder="Например: 'Реализуй новый метод в client.py для...'"></textarea>
                <span class="char-counter">0 chars</span>
            </div>
        </div>
        <div class="compose-field">
            <label for="promptTemplate">2. Шаблон вывода (финальные инструкции)</label>
            <div class="compose-field-wrapper">
                <textarea id="promptTemplate"></textarea>
                <span class="char-counter">0 chars</span>
            </div>
        </div>
    </div>`;

    const templateTextarea = container.querySelector('#promptTemplate');
    templateTextarea.value = 'Приведи ПОЛНЫЙ КОД ТОЛЬКО ЗАТРОНУТЫХ ФАЙЛОВ, чтобы я заменил его без вмешательств. ПРОЯВИ ВЕСЬ СВОЙ ПРОФЕССИОНАЛИЗМ. Спасибо! ULTRATHINK!';
    container.querySelectorAll('.compose-field-wrapper').forEach(enhanceTextarea);

    container.querySelector('#addContextBtn').addEventListener('click', openContext7SearchModal);

    const modalContent = container.closest('.litsync-modal-content');
    if (modalContent && !modalContent.querySelector('.litsync-modal-footer')) {
        const footer = document.createElement('div');
        footer.className = 'litsync-modal-footer';
        footer.innerHTML = `<button id="sendToChatBtn" class="litsync-btn litsync-btn-primary">Отправить в чат</button>`;
        modalContent.appendChild(footer);
    }

    modalContent.querySelector('#sendToChatBtn').addEventListener('click', async (e) => {
        const button = e.currentTarget;
        button.disabled = true;
        button.innerHTML = `${ICONS.progress_activity} Генерация...`;

        try {
            const promptTask = container.querySelector('#promptTask').value;
            const promptTemplate = container.querySelector('#promptTemplate').value;
            if (!promptTask) {
                showNotification('Пожалуйста, опишите вашу задачу в первом поле.', 'error');
                container.querySelector('#promptTask').focus();
                return;
            }

            const promptResponse = await sendMessageToBackground({
                type: 'GENERATE_PROMPT',
                payload: {
                    files: promptCrafterState.filesWithContent,
                    clientId: promptCrafterState.selectedClient.id,
                    docs: promptCrafterState.selectedDocs,
                }
            });
            const generatedPrompt = promptResponse.data.prompt;
            const finalPrompt = `${generatedPrompt}\n\n\n\n${promptTask}\n\n${promptTemplate}`;

            await handleSendToChat(finalPrompt);
            closeModal();
        } catch (error) {
            showNotification(`Ошибка при отправке в чат: ${error.message}`, 'error');
        } finally {
            button.disabled = false;
            button.textContent = 'Отправить в чат';
        }
    });

    updateAddedDocsUI();
}

function updateAddedDocsUI() {
    const container = document.getElementById('context7-pills-container');
    if (!container) return;
    const modalContent = container.closest('.litsync-modal-content');

    animateModalResize(modalContent, () => {
        container.innerHTML = '';
        if (promptCrafterState.selectedDocs.length === 0) {
            container.innerHTML = `<p class="empty-pills-text">Здесь появится документация, добавленная в контекст.</p>`;
            return;
        }
        promptCrafterState.selectedDocs.forEach(doc => {
            const pill = document.createElement('div');
            pill.className = 'context-pill';
            pill.innerHTML = `
                <span class="pill-icon">${ICONS.chip}</span>
                <span class="pill-title">${doc.title}</span>
                <span class="pill-tokens">${formatTokens(doc.totalTokens)}</span>
                <button class="pill-remove-btn" title="Удалить">${ICONS.close}</button>
            `;
            pill.querySelector('.pill-remove-btn').addEventListener('click', () => {
                promptCrafterState.selectedDocs = promptCrafterState.selectedDocs.filter(d => d.id !== doc.id);
                updateAddedDocsUI();
            });
            container.appendChild(pill);
        });
    });
}

async function openContext7SearchModal() {
    const modal = createModal('Добавить документацию из Context7', {size: 'md', isSecondary: true});
    const body = modal.querySelector('.litsync-modal-body');

    await animateModalResize(modal, () => {
        body.innerHTML = `
            <div class="context7-search-view">
                <div class="context7-search-bar">
                    <input type="text" id="context7SearchInput" placeholder="Найти библиотеку (например, httpx, pydantic)...">
                    <button id="context7SearchBtn" class="litsync-btn litsync-btn-primary">${ICONS.search} Найти</button>
                </div>
                <div id="context7ResultsContainer" class="context7-results-container">
                    <p class="empty-pills-text">Результаты поиска появятся здесь.</p>
                </div>
            </div>
        `;
    });

    const searchInput = body.querySelector('#context7SearchInput');
    const searchBtn = body.querySelector('#context7SearchBtn');

    const performSearch = async () => {
        const query = searchInput.value.trim();
        if (!query) return;

        const resultsContainer = body.querySelector('#context7ResultsContainer');
        searchBtn.disabled = true;

        await animateModalResize(modal, () => {
            resultsContainer.innerHTML = Array(3).fill(renderSkeletonCard()).join('');
        });

        try {
            const response = await sendMessageToBackground({type: 'CONTEXT7_SEARCH', payload: {query}});
            await animateModalResize(modal, () => {
                renderContext7Results(resultsContainer, response.data.results);
            });
        } catch (error) {
            await animateModalResize(modal, () => {
                renderError(resultsContainer, `Ошибка поиска: ${error.message}`);
            });
        } finally {
            searchBtn.disabled = false;
        }
    };

    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') performSearch();
    });
}

function renderSkeletonCard() {
    return ` <div class="context7-result-card is-loading"> <div class="card-main"> <div class="skeleton skeleton-title"></div> <div class="skeleton skeleton-desc"></div> <div class="skeleton skeleton-desc-short"></div> </div> <div class="card-meta"> <div class="skeleton skeleton-tag"></div> </div> </div> `;
}

function renderContext7Results(container, results) {
    if (!results || results.length === 0) {
        renderError(container, 'Ничего не найдено по вашему запросу.');
        return;
    }
    container.innerHTML = '';
    results.forEach(result => {
        const card = document.createElement('div');
        card.className = 'context7-result-card';
        const isAlreadyAdded = promptCrafterState.selectedDocs.some(d => d.id === result.id);

        card.innerHTML = `
            <div class="card-main">
                <h4 class="card-title">${result.title}</h4>
                <p class="card-description">${result.description}</p>
            </div>
            <div class="card-meta">
                <span class="card-tag">${ICONS.chip} ${formatTokens(result.totalTokens)}</span>
            </div>
            <div class="card-actions">
                <button class="card-action-btn quick-add-btn" title="Быстрое добавление" ${isAlreadyAdded ? 'disabled' : ''}>
                    ${isAlreadyAdded ? ICONS.check : ICONS.add_circle}
                </button>
                <button class="card-action-btn details-btn" title="Подробнее">${ICONS.article}</button>
            </div>
        `;

        const quickAddBtn = card.querySelector('.quick-add-btn');
        quickAddBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            quickAddBtn.innerHTML = ICONS.progress_activity;
            quickAddBtn.disabled = true;
            try {
                await addDocToContext(result);
                closeModal(`.${SECONDARY_MODAL_OVERLAY_CLASS}`);
                updateAddedDocsUI();
            } catch (error) {
                showNotification(`Не удалось добавить документацию: ${error.message}`, 'error');
                quickAddBtn.innerHTML = ICONS.add_circle;
                quickAddBtn.disabled = false;
            }
        });

        card.querySelector('.details-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            openDocDetailsModal(result);
        });
        container.appendChild(card);
    });
}

async function addDocToContext(docInfo) {
    if (promptCrafterState.selectedDocs.some(d => d.id === docInfo.id)) {
        showNotification(`Библиотека "${docInfo.title}" уже добавлена.`, 'info');
        return;
    }
    showNotification(`Загрузка "${docInfo.title}"...`, 'info');
    const response = await sendMessageToBackground({type: 'CONTEXT7_GET_DOC', payload: {libraryId: docInfo.id}});
    const fullDoc = {
        id: docInfo.id,
        title: docInfo.title,
        totalTokens: docInfo.totalTokens,
        content: response.data.content
    };
    promptCrafterState.selectedDocs.push(fullDoc);
    showNotification(`"${docInfo.title}" добавлена в контекст.`, 'success');
}

async function openDocDetailsModal(docInfo) {
    const modal = createModal(`Документация: ${docInfo.title}`, {size: 'lg', isSecondary: true});
    const body = modal.querySelector('.litsync-modal-body');

    await animateModalResize(modal, () => renderLoading(body, 'Загрузка полной документации...'));

    try {
        const response = await sendMessageToBackground({type: 'CONTEXT7_GET_DOC', payload: {libraryId: docInfo.id}});
        const content = response.data.content;
        const isAlreadyAdded = promptCrafterState.selectedDocs.some(d => d.id === docInfo.id);

        await animateModalResize(modal, () => {
            body.innerHTML = `
                <div class="context7-details-view">
                    <div class="details-meta">
                        <span>${ICONS.chip} <strong>Токены:</strong> ${formatTokens(docInfo.totalTokens)}</span>
                    </div>
                    <textarea readonly class="details-content"></textarea>
                </div>
            `;
            const textarea = body.querySelector('.details-content');
            textarea.value = content;
            enhanceTextarea(textarea.parentElement);

            const footer = document.createElement('div');
            footer.className = 'litsync-modal-footer';
            const addBtn = document.createElement('button');
            addBtn.className = 'litsync-btn litsync-btn-primary';
            addBtn.innerHTML = isAlreadyAdded ? `${ICONS.check} Уже добавлено` : `${ICONS.add_circle} Добавить в контекст`;
            addBtn.disabled = isAlreadyAdded;
            footer.appendChild(addBtn);
            modal.appendChild(footer);

            addBtn.addEventListener('click', async () => {
                addBtn.disabled = true;
                addBtn.innerHTML = ICONS.progress_activity;
                await addDocToContext(docInfo);
                closeModal(`.${SECONDARY_MODAL_OVERLAY_CLASS}`);
                updateAddedDocsUI();
            });
        });

    } catch (error) {
        await animateModalResize(modal, () => renderError(body, `Не удалось загрузить документацию: ${error.message}`));
    }
}

function enhanceTextarea(wrapper) {
    const textarea = wrapper.querySelector('textarea');
    const charCounter = wrapper.querySelector('.char-counter');
    if (!textarea) return;
    const updateCounter = () => {
        if (charCounter) {
            charCounter.textContent = `${textarea.value.length} chars`;
        }
    };
    const autoGrow = () => {
        textarea.style.height = 'auto';
        textarea.style.height = (textarea.scrollHeight) + 'px';
    };
    textarea.addEventListener('input', autoGrow);
    setTimeout(autoGrow, 0);
    if (charCounter) {
        textarea.addEventListener('input', updateCounter);
        updateCounter();
    }
}

async function handleSendToChat(text) {
    const textarea = document.querySelector(PROMPT_TEXTAREA_SELECTOR);
    const sendButton = document.querySelector(PROMPT_SEND_BUTTON_SELECTOR);
    if (!textarea || !sendButton) {
        showNotification('Ошибка: не удалось найти поле ввода или кнопку отправки.', 'error');
        return;
    }
    textarea.value = text;
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    textarea.dispatchEvent(new Event('change', { bubbles: true }));
    textarea.focus();
    setTimeout(() => {
        sendButton.click();
        showNotification('Промпт успешно отправлен в чат.', 'success');
    }, 100);
}

// --- НОВЫЙ МОДУЛЬ: Response Completion Watcher (v4, State Machine) ---

/**
 * Основной "тик" машины состояний, который проверяет статус генерации.
 */
async function watcherTick() {
    const runButton = document.querySelector(PROMPT_SEND_BUTTON_SELECTOR);
    if (!runButton) return; // Если кнопки нет, ничего не делаем

    const isCurrentlyGenerating = runButton.textContent.includes('Stop');

    // --- Переход из IDLE в GENERATING ---
    if (watcherSystem.status === 'IDLE' && isCurrentlyGenerating) {
        watcherSystem.status = 'GENERATING';
        console.log('%c[LitSync Watcher]%c 🔥 RESPONSE STARTED', 'color: #A076F9; font-weight: bold;', 'color: orange; font-weight: bold;');
        
        // Сбрасываем состояние и загружаем актуальные настройки
        watcherSystem.lastContentLength = -1;
        watcherSystem.stableSince = null;
        const { soundSettings } = await chrome.storage.sync.get({
            soundSettings: { enabled: false, sound: 'complete1', volume: 0.5 }
        });
        watcherSystem.soundSettings = soundSettings;
        console.log('%c[LitSync Watcher]%c Settings loaded:', 'color: #A076F9; font-weight: bold;', 'color: inherit;', watcherSystem.soundSettings);
        return; // Завершаем тик, основная работа начнется в следующем
    }

    // --- Работа в состоянии GENERATING ---
    if (watcherSystem.status === 'GENERATING') {
        // Обновляем состояние стабильности текста
        const responseContainers = document.querySelectorAll(MESSAGE_CONTAINER_SELECTOR);
        const latestContainer = responseContainers[responseContainers.length - 1];
        if (latestContainer) {
            const contentArea = latestContainer.querySelector(CONTENT_AREA_SELECTOR);
            const currentLength = contentArea ? contentArea.textContent.length : 0;

            if (currentLength > watcherSystem.lastContentLength) {
                watcherSystem.stableSince = null; // Текст растет, сбрасываем таймер
                watcherSystem.lastContentLength = currentLength;
            } else if (watcherSystem.stableSince === null) {
                watcherSystem.stableSince = Date.now(); // Текст перестал расти, запускаем таймер
            }
        }
        
        const timeStable = watcherSystem.stableSince ? Date.now() - watcherSystem.stableSince : 'N/A';
        console.log(`%c[LitSync Watcher Tick]%c Status: GENERATING, Button has "Stop": ${isCurrentlyGenerating}, Stable for: ${timeStable}ms`, 'color: #A076F9; font-weight: bold;', 'color: cyan;');

        // Проверяем условия завершения
        if (!isCurrentlyGenerating && watcherSystem.stableSince && (Date.now() - watcherSystem.stableSince >= RESPONSE_DEBOUNCE_MS)) {
            console.log('%c[LitSync Watcher]%c ✅ RESPONSE FINISHED (Button has "Run" + text is stable)', 'color: #A076F9; font-weight: bold;', 'color: #34D399; font-weight: bold;');
            if (watcherSystem.soundSettings && watcherSystem.soundSettings.enabled) {
                playCompletionSound(watcherSystem.soundSettings);
            }
            watcherSystem.status = 'IDLE'; // Возвращаемся в режим ожидания
        }
    }
}


/**
 * Воспроизводит звук завершения.
 * @param {object} settings - Настройки звука { sound, volume }.
 */
function playCompletionSound(settings) {
    try {
        console.log(`%c[LitSync Watcher]%c 🔊 Playing sound '${settings.sound}.ogg' at volume ${settings.volume}`, 'color: #A076F9; font-weight: bold;', 'color: #34D399; font-weight: bold;');
        const audio = new Audio(chrome.runtime.getURL(`audio/${settings.sound}.ogg`));
        audio.volume = settings.volume;
        audio.play().catch(e => console.warn('LitSync: Воспроизведение звука было заблокировано браузером.', e));
        audio.onended = () => audio.remove();
    } catch (error) {
        console.error('LitSync: Ошибка при создании или воспроизведении аудио.', error);
    }
}

function initializeWatcherSystem() {
    if (watcherSystem.intervalId) {
        clearInterval(watcherSystem.intervalId);
    }
    console.log('%c[LitSync Watcher]%c Initializing State Machine...', 'color: #A076F9; font-weight: bold;', 'color: inherit;');
    watcherSystem.intervalId = setInterval(watcherTick, WATCHER_TICK_INTERVAL_MS);
}

function dismantleWatcherSystem() {
    if (watcherSystem.intervalId) {
        clearInterval(watcherSystem.intervalId);
        watcherSystem.intervalId = null;
        console.log('%c[LitSync Watcher]%c State Machine dismantled.', 'color: #A076F9; font-weight: bold;', 'color: gray;');
    }
}

function showNotification(message, type = 'success') {
    const container = document.getElementById('litsync-notification-container');
    if (!container) return;
    const notification = document.createElement('div');
    notification.className = `litsync-notification ${type}`;
    notification.innerHTML = ` ${type === 'success' ? ICONS.check_circle : (type === 'info' ? ICONS.progress_activity : ICONS.error)} <span>${message}</span> `;
    if (type === 'info') {
        notification.querySelector('svg').classList.add('spinner');
    }
    container.appendChild(notification);
    setTimeout(() => notification.classList.add('show'), 10);
    setTimeout(() => {
        notification.classList.remove('show');
        notification.addEventListener('transitionend', () => notification.remove(), { once: true });
    }, NOTIFICATION_TIMEOUT);
}

function loadHighlighter() {
    if (highlighterPromise) {
        return highlighterPromise;
    }
    highlighterPromise = new Promise(async (resolve, reject) => {
        try {
            if (window.hljs) {
                return resolve(window.hljs);
            }
            const cssUrl = chrome.runtime.getURL('atom-one-dark.min.css');
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = cssUrl;
            document.head.appendChild(link);
            const scriptUrl = chrome.runtime.getURL('highlight.min.js');
            const hljsModule = await import(chrome.runtime.getURL('highlight.min.js'));
            const hljs = window.hljs || hljsModule.default;
            if (!hljs) {
                throw new Error("Объект `hljs` не найден после загрузки модуля.");
            }
            resolve(hljs);
        } catch (error) {
            console.error('LitSync: Критическая ошибка при загрузке highlight.js.', error);
            reject(error);
        }
    });
    return highlighterPromise;
}

// --- УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ РАСШИРЕНИЯ ---
function initialize() {
    console.log('LitSync v27.0: Инициализация...');
    if (domScannerInterval) return;
    if (!document.getElementById('litsync-notification-container')) {
        const notificationContainer = document.createElement('div');
        notificationContainer.id = 'litsync-notification-container';
        document.body.appendChild(notificationContainer);
    }
    chrome.storage.sync.get({isEnabled: true, isShortenEnabled: false}, (data) => {
        isShortenEnabled = data.isShortenEnabled;
        console.log(`LitSync: Функция сокращения ответов при запуске: ${isShortenEnabled ? 'Включена' : 'Выключена'}.`);
        domScannerInterval = setInterval(scanAndProcessMessages, SCAN_INTERVAL_MS);
    });
    loadHighlighter();
    initializeWatcherSystem(); // <--- ЗАПУСК НОВОЙ СИСТЕМЫ
    console.log('LitSync v27.0: Расширение активно.');
}

function dismantle() {
    if (domScannerInterval) {
        clearInterval(domScannerInterval);
        domScannerInterval = null;
    }
    dismantleWatcherSystem(); // <--- ОЧИСТКА НАБЛЮДАТЕЛЯ
    // Также останавливаем keep_active, если он был запущен
    if (window.LitSyncModules && window.LitSyncModules.keepActive) {
        window.LitSyncModules.keepActive.stop();
    }
    document.querySelectorAll(MESSAGE_CONTAINER_SELECTOR).forEach(container => {
        cleanupShorteningForContainer(container);
    });
    document.querySelectorAll(`.${SYNC_BUTTON_CLASS}, .${CRAFT_BUTTON_CLASS}`).forEach(b => b.remove());
    document.querySelectorAll(`.${PROCESSED_MARKER}`).forEach(el => el.classList.remove(PROCESSED_MARKER));
    document.getElementById('litsync-notification-container')?.remove();
    closeModal();
    console.log('LitSync v27.0: Все элементы расширения удалены.');
}

chrome.storage.sync.get({isEnabled: true}, (data) => {
    if (data.isEnabled) initialize();
});
chrome.storage.onChanged.addListener((changes, namespace) => {
    if (namespace !== 'sync') return;
    if (changes.isEnabled) {
        if (changes.isEnabled.newValue) {
            initialize();
        } else {
            dismantle();
        }
    }
    if (changes.isShortenEnabled) {
        isShortenEnabled = !!changes.isShortenEnabled.newValue;
        console.log(`LitSync: Состояние сокращения ответов изменено на: ${isShortenEnabled}`);
        if (!isShortenEnabled) {
            document.querySelectorAll(MESSAGE_CONTAINER_SELECTOR).forEach(container => {
                cleanupShorteningForContainer(container);
            });
        }
    }
});