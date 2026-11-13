import platform
import logging
import os

# ОС к которым он может подключиться
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# Минимальные размеры элементы
MIN_ELEMENT_WIDTH = 5
MIN_ELEMENT_HEIGHT = 5

# Элемент должен иметь хотя бы такую видимую долю после учёта перекрытий.
MIN_VISIBLE_RATIO = 0.15

# Минимальная реально видимая площадь окна перед запуском дорогого UIA-обхода.
MIN_VISIBLE_WINDOW_AREA = 64

# Полнота важнее искусственного time budget: None означает, что все реально
# видимые окна должны быть обработаны. Защитный timeout не влияет на обычные
# медленные окна и нужен только против зависшего COM provider.
UIA_SCAN_BUDGET_MS = None
UIA_HARD_TIMEOUT_MS = 1000.0

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
