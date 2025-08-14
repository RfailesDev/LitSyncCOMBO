# core/change_detector.py
"""
Модуль для сравнения двух версий текста и генерации структурированного diff.
"""
import difflib
import logging
from typing import Dict, List, Literal, TypedDict, Optional

logger = logging.getLogger(__name__)

# --- Типы для структурированного вывода ---

LineType = Literal["added", "deleted", "context"]


class DiffLine(TypedDict):
    """Представляет одну строку в diff."""
    type: LineType
    line_num_old: Optional[int]
    line_num_new: Optional[int]
    content: str


class DiffHunk(TypedDict):
    """Представляет "ханк" - непрерывный блок изменений."""
    old_start_line: int
    new_start_line: int
    lines: List[DiffLine]


class FileChange(TypedDict):
    """Представляет полный набор изменений для одного файла."""
    path: str
    status: Literal["modified", "added", "deleted", "error"]
    error_message: Optional[str]
    hunks: List[DiffHunk]


class ChangeDetector:
    """
    Создает структурированный diff между двумя строками текста,
    группируя изменения в "ханки" с заданным количеством строк контекста.
    """

    def __init__(self, context_lines: int = 3):
        """
        Инициализирует детектор.

        Args:
            context_lines: Количество строк контекста для отображения
                           до и после блока изменений.
        """
        if not isinstance(context_lines, int) or context_lines < 0:
            raise ValueError("context_lines должен быть неотрицательным целым числом.")
        self._context_lines = context_lines

    def generate_diff(self, old_content: str, new_content: str) -> List[DiffHunk]:
        """
        Основной метод для генерации diff'а.

        Args:
            old_content: Исходное содержимое файла.
            new_content: Новое содержимое файла.

        Returns:
            Список "ханков" (блоков изменений).
        """
        if old_content == new_content:
            return []

        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
        hunks: List[DiffHunk] = []

        for group in matcher.get_grouped_opcodes(self._context_lines):
            first_op, last_op = group[0], group[-1]

            old_start = first_op[1]
            new_start = first_op[3]

            hunk_lines: List[DiffLine] = []

            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    for i in range(i1, i2):
                        hunk_lines.append({
                            "type": "context",
                            "line_num_old": i + 1,
                            "line_num_new": (j1 + (i - i1)) + 1,
                            "content": old_lines[i],
                        })
                else:  # 'replace', 'delete', 'insert'
                    if tag in ("replace", "delete"):
                        for i in range(i1, i2):
                            hunk_lines.append({
                                "type": "deleted",
                                "line_num_old": i + 1,
                                "line_num_new": None,
                                "content": old_lines[i],
                            })
                    if tag in ("replace", "insert"):
                        for j in range(j1, j2):
                            hunk_lines.append({
                                "type": "added",
                                "line_num_old": None,
                                "line_num_new": j + 1,
                                "content": new_lines[j],
                            })

            hunks.append({
                "old_start_line": old_start + 1,
                "new_start_line": new_start + 1,
                "lines": hunk_lines,
            })

        return hunks