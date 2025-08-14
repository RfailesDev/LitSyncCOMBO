# core/parser.py
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TypedDict

logger = logging.getLogger(__name__)


class DebugInfoV7(TypedDict):
    """Структура для отладки парсера V7."""
    parsing_mode: str
    unmatched_code_blocks: int
    final_pairs: List[Dict[str, str]]


class LLMResponseParserV7:
    """
    Надежный парсер для извлечения файлов из текстового ответа LLM.
    Версия 7 улучшает V6, добавляя поддержку нескольких блоков <files>.

    Проблема V6:
    Парсер мог обработать только первый найденный блок <files>...</files>,
    игнорируя все последующие.

    Решение в V7:
    1.  Парсер использует `re.findall` для поиска *всех* вхождений
        блоков `<files>...</files>` в ответе.
    2.  Если блоки найдены, их содержимое извлекается и объединяется
        в единый текст для парсинга.
    3.  **Ключевое улучшение:** Фрагменты из разных блоков объединяются
        через двойной перенос строки (`"\\n\\n"`). Это позволяет использовать
        существующий механизм V6, который воспринимает `\\n\\n` как
        разделитель абзацев, эффективно изолируя контекст каждого
        исходного блока и предотвращая неверное связывание путей и кода
        через границы блоков.
    4.  Если блоки `<files>` не найдены, парсер, как и прежде, работает
        в режиме обработки всего текста ответа (fallback).
    """
    # Regex для поиска всех блоков <files>
    _FILE_BLOCK_REGEX = re.compile(r"<files>(.*?)</files>", re.DOTALL)

    # Regex для поиска блоков кода.
    _CODE_BLOCK_REGEX = re.compile(
        r"^```(?P<lang>\w*)\n"
        r"(?P<code>.*?)\n"
        r"^```\s*$",
        re.DOTALL | re.MULTILINE
    )

    # --- Regex'ы для поиска пути в текстовых фрагментах ---
    _PATH_MARKER_REGEX = re.compile(r"path:\s*`?([^`\n]+?)`?")
    _BACKTICK_PATH_REGEX = re.compile(r"`([^`\n]+?)`")
    _IMPLICIT_PATH_REGEX = re.compile(
        r"^(?<![│├──└])(?!\s*```)(?!\s*path:)(?!\s*`)[^`\n]*[/\\\.][^`\n]*(?<!\s\s)\s*$",
        re.MULTILINE,
    )
    _LIST_ITEM_PATH_REGEX = re.compile(r"^\s*[-*]\s+(`?([^`\n]+?)`?)\s*$")

    @staticmethod
    def _is_likely_path(path: str) -> bool:
        """Проверяет строку с помощью эвристик, чтобы определить, похожа ли она на путь."""
        clean_path = path.strip()
        if not (1 < len(clean_path) < 256):
            return False
        # Запрещаем символы псевдографики в пути
        if any(c in clean_path for c in "│├──└"):
            return False
        p = Path(clean_path)
        has_dot_in_name = "." in p.name
        has_separator = "/" in path or "\\" in path
        return has_dot_in_name or has_separator

    @classmethod
    def _find_path_in_lines(cls, lines: List[str]) -> Optional[str]:
        """Ищет наиболее вероятный путь в списке строк, идя снизу вверх."""
        for line in reversed(lines):
            stripped_line = line.strip()
            if not stripped_line:
                continue

            for pattern in [cls._PATH_MARKER_REGEX, cls._LIST_ITEM_PATH_REGEX]:
                match = pattern.search(stripped_line)
                if match:
                    path = (match.group(2) or match.group(1)).strip()
                    if cls._is_likely_path(path): return path

            matches = list(cls._BACKTICK_PATH_REGEX.finditer(stripped_line))
            if matches:
                path = matches[-1].group(1).strip()
                if cls._is_likely_path(path): return path

            if cls._IMPLICIT_PATH_REGEX.match(stripped_line):
                path = stripped_line
                if cls._is_likely_path(path): return path

        return None

    def parse(self, text: str) -> Tuple[List[Dict[str, str]], DebugInfoV7]:
        """
        Основной метод парсинга.
        Поддерживает несколько блоков <files> и режим fallback.
        """
        parsed_data: List[Dict[str, str]] = []
        debug_info: DebugInfoV7 = {
            "parsing_mode": "Fallback (full text)",
            "unmatched_code_blocks": 0,
            "final_pairs": [],
        }

        # --- КЛЮЧЕВОЕ УЛУЧШЕНИЕ V7 ---
        # Ищем все блоки <files>, а не только первый.
        file_blocks_content = self._FILE_BLOCK_REGEX.findall(text)

        if file_blocks_content:
            # Объединяем содержимое всех найденных блоков через `\n\n`.
            # Это создает семантическую границу, которую парсер уже умеет обрабатывать.
            text_to_parse = "\n\n".join(file_blocks_content)
            num_blocks = len(file_blocks_content)
            plural_s = "s" if num_blocks > 1 else ""
            debug_info["parsing_mode"] = f"Token-based ({num_blocks} <files> block{plural_s})"
            logger.info(f"Обнаружено {num_blocks} блок(а/ов) <files>. Парсинг объединенного содержимого.")
        else:
            text_to_parse = text
            logger.info("Блок <files> не найден. Включен режим фолбэка: парсинг всего текста.")
        # --- КОНЕЦ УЛУЧШЕНИЯ ---

        code_matches = list(self._CODE_BLOCK_REGEX.finditer(text_to_parse))
        last_match_end = 0

        for match in code_matches:
            start_of_search_area = last_match_end
            end_of_search_area = match.start()
            last_match_end = match.end()

            look_behind_text = text_to_parse[start_of_search_area:end_of_search_area]

            last_paragraph_break = look_behind_text.rfind("\n\n")

            if last_paragraph_break != -1:
                search_text = look_behind_text[last_paragraph_break:]
            else:
                search_text = look_behind_text

            search_lines = search_text.splitlines()
            path = self._find_path_in_lines(search_lines)
            code = match.group("code").strip()

            if path:
                pair = {"path": path, "content": code}
                parsed_data.append(pair)
                logger.info(f"Связаны путь '{path}' и блок кода.")
            else:
                debug_info["unmatched_code_blocks"] += 1
                logger.warning(
                    f"Найден блок кода, но для него не найден путь в последнем абзаце. "
                    f"Анализируемый текст:\n---\n{search_text.strip()}\n---"
                )

        debug_info["final_pairs"] = parsed_data

        if not parsed_data and file_blocks_content:
            logger.warning("Не найдено ни одной валидной пары 'путь -> код' внутри блоков <files>.")
        elif not parsed_data:
            logger.warning("Не найдено ни одной валидной пары 'путь -> код' во всем тексте.")


        return parsed_data, debug_info