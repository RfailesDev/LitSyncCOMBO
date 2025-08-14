/**
 * @file popup.js
 * @version 7.0 (Feature: Sound Notifications)
 * @description Управляет логикой всплывающего окна расширения.
 * - Добавлен переключатель для сокращения ответов.
 * - Добавлено поле для конфигурации URL сервера.
 * - Добавлена секция для настройки звуковых уведомлений.
 */

document.addEventListener('DOMContentLoaded', async () => {
    // --- Элементы UI ---
    const enableSwitch = document.getElementById('enableSwitch');
    const shortenResponseSwitch = document.getElementById('shortenResponseSwitch');
    const statusIndicator = document.getElementById('statusIndicator');
    const statusText = statusIndicator.querySelector('.status-text');
    const statusIcon = statusIndicator.querySelector('.status-icon use');
    const serverUrlInput = document.getElementById('serverUrlInput');
    const saveServerUrlBtn = document.getElementById('saveServerUrlBtn');

    // Новые элементы для звука
    const soundEnableSwitch = document.getElementById('soundEnableSwitch');
    const audioConfigSection = document.getElementById('audioConfigSection');
    const soundChoiceRadios = document.querySelectorAll('input[name="soundChoice"]');
    const volumeSlider = document.getElementById('volumeSlider');
    const testSoundBtn = document.getElementById('testSoundBtn');

    // НОВЫЙ элемент для "Держать AIStudio активным"
    const keepActiveSwitch = document.getElementById('keepActiveSwitch');

    const allElements = [
        enableSwitch, shortenResponseSwitch, statusIndicator, serverUrlInput, saveServerUrlBtn,
        soundEnableSwitch, audioConfigSection, volumeSlider, testSoundBtn,
        keepActiveSwitch // Добавляем новый элемент в список для проверки
    ];

    if (allElements.some(el => !el) || soundChoiceRadios.length === 0) {
        console.error("LitSync: Критическая ошибка. Один или несколько элементов UI не найдены в popup.html.");
        document.body.innerHTML = "Ошибка загрузки UI. Попробуйте переустановить расширение.";
        return;
    }

    let testAudio = null; // Для предотвращения одновременного проигрывания

    /**
     * Обновляет UI статуса в соответствии с состоянием (включено/выключено).
     * @param {boolean} isEnabled - Текущее состояние расширения.
     */
    const updateStatusUI = (isEnabled) => {
        enableSwitch.checked = isEnabled;
        if (isEnabled) {
            statusIndicator.classList.remove('disabled');
            statusIndicator.classList.add('enabled');
            statusText.textContent = 'Расширение активно';
            statusIcon.setAttribute('href', '#icon-toggle-on');
        } else {
            statusIndicator.classList.remove('enabled');
            statusIndicator.classList.add('disabled');
            statusText.textContent = 'Расширение отключено';
            statusIcon.setAttribute('href', '#icon-toggle-off');
        }
    };

    /**
     * Сохраняет объект настроек в chrome.storage.sync.
     * @param {object} settings - Объект для сохранения.
     * @returns {Promise<boolean>} - true в случае успеха, false в случае ошибки.
     */
    const saveToStorage = async (settings) => {
        try {
            await chrome.storage.sync.set(settings);
            console.log(`LitSync: Настройки сохранены:`, settings);
            return true;
        } catch (error) {
            console.error(`LitSync: Ошибка сохранения настроек: ${error.message}`);
            return false;
        }
    };

    /**
     * Обрабатывает изменение состояния переключателя.
     * @param {HTMLInputElement} element - Элемент input (checkbox).
     * @param {string} storageKey - Ключ для сохранения.
     * @param {boolean} [sendToBackground=false] - Нужно ли отправлять сообщение в background script.
     */
    const handleToggleChange = async (element, storageKey, sendToBackground = false) => {
        const value = element.checked;
        const success = await saveToStorage({ [storageKey]: value });
        if (!success) {
            element.checked = !value; // Возвращаем в предыдущее состояние
        } else {
            if (storageKey === 'isEnabled') {
                updateStatusUI(value);
            }
            if (sendToBackground) {
                try {
                    await chrome.runtime.sendMessage({
                        type: 'TOGGLE_KEEP_ACTIVE',
                        payload: { enabled: value }
                    });
                } catch (error) {
                    console.error(`LitSync: Ошибка отправки сообщения TOGGLE_KEEP_ACTIVE: ${error.message}`);
                    // Если не удалось отправить, возможно, стоит откатить UI или показать ошибку
                    element.checked = !value;
                    await saveToStorage({ [storageKey]: !value }); // Откатываем в storage
                    if (storageKey === 'isEnabled') updateStatusUI(!value);
                }
            }
        }
    };

    /**
     * Сохраняет URL сервера.
     */
    const handleSaveServerUrl = async () => {
        let url = serverUrlInput.value.trim();
        if (url && !url.match(/^https?:\/\//)) {
            url = 'http://' + url; // Добавляем http по умолчанию, если протокол отсутствует
        }
        serverUrlInput.value = url; // Обновляем поле ввода
        await saveToStorage({ 'serverUrl': url });
        // Показываем визуальную обратную связь
        saveServerUrlBtn.classList.add('success');
        setTimeout(() => saveServerUrlBtn.classList.remove('success'), 1500);
    };

    /**
     * Собирает и сохраняет все настройки звука.
     */
    const saveSoundSettings = async () => {
        const selectedRadio = document.querySelector('input[name="soundChoice"]:checked');
        const settings = {
            soundSettings: {
                enabled: soundEnableSwitch.checked,
                sound: selectedRadio ? selectedRadio.value : 'complete1',
                volume: parseFloat(volumeSlider.value)
            }
        };
        audioConfigSection.classList.toggle('hidden', !settings.soundSettings.enabled);
        await saveToStorage(settings);
    };

    /**
     * Проигрывает тестовый звук на основе текущих настроек UI.
     */
    const playTestSound = () => {
        if (testAudio && !testAudio.paused) {
            testAudio.pause();
            testAudio.currentTime = 0;
        }
        const selectedSound = document.querySelector('input[name="soundChoice"]:checked').value;
        const volume = parseFloat(volumeSlider.value);
        
        testAudio = new Audio(chrome.runtime.getURL(`audio/${selectedSound}.ogg`));
        testAudio.volume = volume;
        testAudio.play().catch(e => console.error("LitSync: Не удалось воспроизвести тестовый звук.", e));
    };

    // --- Инициализация ---

    // 1. Добавляем обработчики событий
    enableSwitch.addEventListener('change', () => handleToggleChange(enableSwitch, 'isEnabled'));
    shortenResponseSwitch.addEventListener('change', () => handleToggleChange(shortenResponseSwitch, 'isShortenEnabled'));
    saveServerUrlBtn.addEventListener('click', handleSaveServerUrl);
    serverUrlInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleSaveServerUrl();
    });

    // НОВЫЙ обработчик для keepActiveSwitch
    keepActiveSwitch.addEventListener('change', () => handleToggleChange(keepActiveSwitch, 'keepActiveEnabled', true));

    // Обработчики для звука
    soundEnableSwitch.addEventListener('change', saveSoundSettings);
    soundChoiceRadios.forEach(radio => radio.addEventListener('change', saveSoundSettings));
    volumeSlider.addEventListener('input', saveSoundSettings);
    testSoundBtn.addEventListener('click', playTestSound);

    // 2. Загружаем начальное состояние из хранилища
    try {
        const data = await chrome.storage.sync.get({
            isEnabled: true,
            isShortenEnabled: false,
            serverUrl: 'http://darkserver-eu.ru:6032',
            soundSettings: {
                enabled: false,
                sound: 'complete1',
                volume: 1
            },
            keepActiveEnabled: false // НОВАЯ настройка по умолчанию
        });

        // Основные настройки
        updateStatusUI(data.isEnabled);
        shortenResponseSwitch.checked = data.isShortenEnabled;
        serverUrlInput.value = data.serverUrl;

        // НОВАЯ настройка
        keepActiveSwitch.checked = data.keepActiveEnabled;

        // Настройки звука
        const { enabled, sound, volume } = data.soundSettings;
        soundEnableSwitch.checked = enabled;
        audioConfigSection.classList.toggle('hidden', !enabled);
        volumeSlider.value = volume;
        const radioToCheck = document.querySelector(`input[name="soundChoice"][value="${sound}"]`);
        if (radioToCheck) {
            radioToCheck.checked = true;
        }

    } catch (error) {
        console.error(`LitSync: Ошибка загрузки состояния: ${error.message}`);
        // В случае ошибки, устанавливаем UI в состояние по умолчанию
        updateStatusUI(false);
        shortenResponseSwitch.checked = false;
        serverUrlInput.value = 'http://darkserver-eu.ru:6032';
        soundEnableSwitch.checked = false;
        audioConfigSection.classList.add('hidden');
        keepActiveSwitch.checked = false; // Сброс новой настройки
    }
});