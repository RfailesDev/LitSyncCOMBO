# core/prompt_builder.py
"""
Модуль для генерации текстового промпта из структуры проекта и дополнительной документации.
Версия 3.0: Добавлена поддержка контекста из документации.
"""
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class PromptBuilder:
    """
    Формирует единый текстовый блок, описывающий структуру и содержимое
    выбранных файлов проекта, а также дополнительную документацию для передачи в LLM.
    """

    @staticmethod
    def _generate_structure_tree(files: List[Dict[str, Any]], root_name: str) -> str:
        """
        Создает текстовое представление дерева файлов из плоского списка путей.
        """
        tree = {}
        for file_info in files:
            path = file_info["path"]
            parts = path.split("/")
            current_level = tree
            for part in parts:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]

        def build_lines(d: dict, prefix: str = "") -> List[str]:
            lines = []
            entries = sorted(d.keys())
            for i, entry in enumerate(entries):
                connector = "└── " if i == len(entries) - 1 else "├── "
                lines.append(f"{prefix}{connector}{entry}")
                if d[entry]:
                    extension = "│   " if i < len(entries) - 1 else "    "
                    lines.extend(build_lines(d[entry], prefix + extension))
            return lines

        return f"{root_name}/\n" + "\n".join(build_lines(tree))

    @staticmethod
    def _format_documentation(docs: List[Dict[str, Any]]) -> str:
        """
        Форматирует блок с дополнительной документацией.
        """
        if not docs:
            return ""

        doc_parts = []
        for doc in docs:
            title = doc.get('title', 'Unknown Library')
            content = doc.get('content', 'No content available.')
            doc_parts.append(
                f"Documentation for: {title}\n"
                f"```\n{content}\n```"
            )

        return (
            "ADDITIONAL CONTEXT FROM DOCUMENTATION:\n\n"
            f"{'\n\n'.join(doc_parts)}"
        )

    def build(
        self,
        files: List[Dict[str, Any]],
        root_name: str = "project",
        docs: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Основной метод, генерирующий полный текст промпта.

        Args:
            files: Список словарей, где каждый словарь содержит {'path': str, 'content': str | None}.
            root_name: Реальное имя корневой папки проекта.
            docs: Опциональный список словарей с документацией. Каждый словарь
                  должен содержать {'title': str, 'content': str}.

        Returns:
            Отформатированная строка для LLM.
        """
        try:
            # Шаг 1: Генерируем дерево из ВСЕХ файлов.
            structure_str = self._generate_structure_tree(files, root_name) if files else ""

            # Шаг 2: Фильтруем файлы для секции с содержимым.
            files_with_content = [f for f in files if f.get("content") is not None] if files else []

            # Шаг 3: Генерируем блок с содержимым только для отфильтрованных файлов.
            files_content_parts = []
            for file_info in sorted(files_with_content, key=lambda x: x['path']):
                path = file_info["path"]
                content = file_info["content"]
                extension = path.split('.')[-1] if '.' in path else 'txt'
                files_content_parts.append(f"{path}\n```{extension}\n{content}\n```")
            files_content_str = "\n\n\n".join(files_content_parts)

            # Шаг 4: Форматируем дополнительную документацию.
            docs_str = self._format_documentation(docs or [])

            # Шаг 5: Собираем финальный промпт.
            prompt_parts = []
            if structure_str:
                prompt_parts.append(f"Project structure ({root_name}):\n\n{structure_str}")
            if files_content_str:
                prompt_parts.append(f"Project files:\n\n{files_content_str}")
            if docs_str:
                prompt_parts.append(docs_str)

            return "\n\n\n---\n\n\n".join(prompt_parts)

        except Exception as e:
            logger.error(f"Ошибка при сборке промпта: {e}", exc_info=True)
            return f"Error building prompt: {e}"