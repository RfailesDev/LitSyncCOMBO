# pathfilter.py
"""
Модуль для фильтрации путей на основе правил из .gitignore файлов.

Версия 2.0: Исправлена критическая ошибка в логике сборки правил,
которая приводила к некорректной фильтрации. Теперь правила из вложенных
.gitignore файлов корректно привязываются к их директориям.

Использует библиотеку `pathspec` для корректного и эффективного
парсинга и сопоставления.
"""
import logging
from pathlib import Path
from typing import Iterable

import pathspec
from pathspec.patterns import GitWildMatchPattern


class GitignoreFilter:
    """
    Класс, который находит, парсит и применяет правила из .gitignore файлов.
    """

    def __init__(self, root_dir: Path):
        """
        Инициализирует фильтр, находя и компилируя все .gitignore файлы в проекте.

        Args:
            root_dir: Корневая директория проекта для сканирования.
        """
        self.root_dir = root_dir.resolve()
        self.spec = self._build_spec()

    def _find_gitignore_files(self) -> Iterable[Path]:
        """Находит все .gitignore файлы, начиная от корневой директории."""
        return self.root_dir.rglob(".gitignore")

    def _build_spec(self) -> pathspec.PathSpec:
        """
        Собирает правила из всех найденных .gitignore файлов и компилирует их
        в один объект PathSpec для эффективного сопоставления.

        Этот метод корректно обрабатывает вложенные .gitignore файлы,
        привязывая их правила к соответствующим директориям.
        """
        all_patterns: list[str] = []
        gitignore_files = self._find_gitignore_files()
        logging.info(f"Найдено {len(list(self.root_dir.rglob('.gitignore')))} .gitignore файлов для обработки.")

        for gitignore_path in gitignore_files:
            try:
                with gitignore_path.open("r", encoding="utf-8") as f:
                    # Директория, в которой находится текущий .gitignore.
                    # Все правила в этом файле будут относиться к ней.
                    base_dir = gitignore_path.parent

                    for line in f:
                        pattern = line.strip()
                        if not pattern or pattern.startswith("#"):
                            continue

                        # Если паттерн начинается с '!', это правило-исключение.
                        # Его нужно оставить как есть, но добавить префикс директории.
                        is_negation = pattern.startswith("!")
                        if is_negation:
                            pattern = pattern[1:]

                        # Если паттерн содержит '/', он уже считается привязанным
                        # к директории .gitignore. Если нет, он работает рекурсивно.
                        # Мы должны преобразовать его в паттерн, который будет
                        # работать от корня нашего проекта.
                        
                        # Путь к директории .gitignore относительно корня проекта
                        relative_base_dir = base_dir.relative_to(self.root_dir)

                        # Собираем новый, "абсолютизированный" паттерн
                        if relative_base_dir == Path("."):
                            # .gitignore в корне проекта
                            full_pattern = pattern
                        else:
                            # .gitignore во вложенной директории
                            # as_posix() для использования '/' в качестве разделителя
                            full_pattern = f"{relative_base_dir.as_posix()}/{pattern}"
                        
                        if is_negation:
                            full_pattern = "!" + full_pattern
                        
                        all_patterns.append(full_pattern)

            except Exception as e:
                logging.warning(f"Не удалось прочитать или обработать {gitignore_path}: {e}")
        
        # Добавляем "родные" директории для игнорирования в самый конец.
        # Это гарантирует, что .git всегда будет игнорироваться.
        all_patterns.append(".git/")
        
        logging.debug(f"Скомпилированные .gitignore паттерны: {all_patterns}")
        
        # Создаем спецификацию из всех собранных и нормализованных паттернов
        return pathspec.PathSpec.from_lines(GitWildMatchPattern, all_patterns)

    def is_ignored(self, path: Path) -> bool:
        """
        Проверяет, должен ли данный путь быть проигнорирован согласно правилам.

        Args:
            path: Абсолютный или относительный путь к файлу или директории.

        Returns:
            True, если путь должен быть проигнорирован, иначе False.
        """
        try:
            # pathspec лучше всего работает с путями, относительными к корню,
            # от которого строились паттерны.
            path_to_check = path.relative_to(self.root_dir) if path.is_absolute() else path
            return self.spec.match_file(path_to_check)
        except Exception as e:
            # Это может произойти, если path находится вне self.root_dir
            logging.debug(f"Ошибка при проверке пути '{path}': {e}. Путь может быть вне проекта.")
            # Если путь вне проекта, его следует считать "игнорируемым"
            # с точки зрения проекта. Но для безопасности вернем False.
            return False