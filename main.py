import cProfile
import pstats
import io
import time

from scanner import DesktopScanner


def main():
    scanner = DesktopScanner()
    scanner.scan()


if __name__ == "__main__":
    profiler = cProfile.Profile()
    profiler.enable()

    main()

    profiler.disable()

    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.sort_stats("cumulative")
    ps.print_stats(30)  # 30 функций медленных

    print(s.getvalue())