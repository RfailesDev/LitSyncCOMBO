/**
 * @file background.js
 * @version 4.0 (Feature: Context7 Integration & Configurable Server)
 * @description Service Worker, который выступает в роли безопасного прокси.
 * - Добавлена возможность указывать URL сервера.
 * - Добавлены обработчики для нового Context7 API.
 * - Обновлен `generatePrompt` для передачи документации.
 */

const DEFAULT_SERVER_URL = 'http://darkserver-eu.ru:6032';

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('Background: получено сообщение', message);

    (async () => {
        try {
            let responseData;
            switch (message.type) {
                // --- LitSync Core API ---
                case 'GET_CLIENTS':
                    responseData = await handleGetClients();
                    break;
                case 'PREVIEW_SYNC':
                    responseData = await handlePreviewSync(message.payload);
                    break;
                case 'SYNC_DATA':
                    responseData = await handleSyncData(message.payload);
                    break;
                case 'GET_FILE_TREE':
                    responseData = await handleGetFileTree(message.payload);
                    break;
                case 'GET_FILE_CONTENT':
                    responseData = await handleGetFileContent(message.payload);
                    break;
                case 'GENERATE_PROMPT':
                    responseData = await handleGeneratePrompt(message.payload);
                    break;
                // --- НОВЫЕ: Context7 API ---
                case 'CONTEXT7_SEARCH':
                    responseData = await handleContext7Search(message.payload);
                    break;
                case 'CONTEXT7_GET_DOC':
                    responseData = await handleContext7GetDoc(message.payload);
                    break;
                // --- НОВОЕ: Keep Active API ---
                case 'TOGGLE_KEEP_ACTIVE':
                    responseData = await handleToggleKeepActive(message.payload);
                    break;
                default:
                    throw new Error(`Неизвестный тип сообщения: ${message.type}`);
            }
            sendResponse({ success: true, data: responseData });
        } catch (error) {
            console.error(`Background (type: ${message.type}):`, error);
            sendResponse({ success: false, error: error.message });
        }
    })();

    return true; // Keep the message channel open for async response
});

async function getServerUrl() {
    try {
        const { serverUrl } = await chrome.storage.sync.get('serverUrl');
        return serverUrl || DEFAULT_SERVER_URL;
    } catch (e) {
        return DEFAULT_SERVER_URL;
    }
}

async function apiFetch(endpoint, options = {}) {
    const serverUrl = await getServerUrl();
    const fullUrl = `${serverUrl}${endpoint}`;
    console.log(`Background: Выполняю запрос к ${fullUrl}`);
    const response = await fetch(fullUrl, options);
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.error || `Ошибка сервера: ${response.statusText} (${response.status})`);
    }
    return result;
}

// --- LitSync Handlers ---

async function handleGetClients() {
    return await apiFetch('/api/clients');
}

async function handlePreviewSync(payload) {
    return await apiFetch('/api/sync/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
}

async function handleSyncData(payload) {
    return await apiFetch('/api/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
}

async function handleGetFileTree(payload) {
    return await apiFetch(`/api/clients/${payload.clientId}/file_tree`);
}

async function handleGetFileContent(payload) {
    return await apiFetch(`/api/clients/${payload.clientId}/file_content`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths: payload.paths }),
    });
}

async function handleGeneratePrompt(payload) {
    if (!payload || !Array.isArray(payload.files) || !payload.clientId) {
        throw new Error('Некорректные данные для генерации промпта.');
    }
    // Передаем `files`, `clientId` и новую `docs`
    return await apiFetch('/api/prompt/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
}

// --- НОВЫЕ: Context7 Handlers ---

async function handleContext7Search(payload) {
    if (!payload || !payload.query) {
        throw new Error('Не указан поисковый запрос для Context7.');
    }
    const encodedQuery = encodeURIComponent(payload.query);
    return await apiFetch(`/api/context7/search?query=${encodedQuery}`);
}

async function handleContext7GetDoc(payload) {
    if (!payload || !payload.libraryId) {
        throw new Error('Не указан ID библиотеки для Context7.');
    }
    // ID может содержать '/', поэтому не кодируем его полностью, а позволяем fetch сделать это.
    return await apiFetch(`/api/context7/docs/${payload.libraryId}`);
}

// --- НОВОЕ: Keep Active Handler ---
async function handleToggleKeepActive(payload) {
    const { enabled } = payload;
    // Находим все вкладки AIStudio
    const tabs = await chrome.tabs.query({ url: "https://aistudio.google.com/*" });
    if (tabs.length > 0) {
        for (const tab of tabs) {
            try {
                // Отправляем сообщение в content script каждой вкладки AIStudio
                await chrome.tabs.sendMessage(tab.id, {
                    type: 'TOGGLE_KEEP_ACTIVE',
                    payload: { enabled }
                });
                console.log(`Background: Отправлено TOGGLE_KEEP_ACTIVE=${enabled} в таб ${tab.id}`);
            } catch (error) {
                // Логируем ошибку, но не прерываем процесс для других вкладок
                console.error(`Background: Ошибка отправки сообщения в content script таба ${tab.id}:`, error);
            }
        }
        return { status: 'success', tabsProcessed: tabs.length, enabled };
    } else {
        console.warn('Background: Вкладки AIStudio не найдены для TOGGLE_KEEP_ACTIVE.');
        return { status: 'no_aistudio_tabs' };
    }
}


console.log('Background Service Worker запущен (v4.0).');