import platform
import logging
import os

# ОС к которым он может подключиться
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# Минимальные размеры элементы
MIN_ELEMENT_WIDTH = 5
MIN_ELEMENT_HEIGHT = 5

# Смещения текста/номера прямоугольника
TEXT_OFFSET_Y = 11

# Диапазон выбора цвета
COLOR_MIN = 70
COLOR_MAX = 220

# Названия папок для сохранения выходных файлов
RESULTS_DIR = "results"
SCREENSHOT_DIR = os.path.join(RESULTS_DIR, "screenshots")
JSON_DIR = os.path.join(RESULTS_DIR, "json-files")

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("ui_scanner")
