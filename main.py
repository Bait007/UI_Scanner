import argparse
import cProfile
import io
import pstats

from scanner import DesktopScanner


def parse_args():
    parser = argparse.ArgumentParser(description="Scan visible desktop UI elements")
    parser.add_argument(
        "--profile",
        action="store_true",
        help="print cProfile statistics for scan(), disabled by default",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="measure the in-memory snapshot without JPEG/JSON persistence",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="run multiple scans with the same warm UIA worker",
    )
    return parser.parse_args()


def run_profiled(scanner: DesktopScanner):
    profiler = cProfile.Profile()
    profiler.enable()
    result = scanner.scan()
    profiler.disable()

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(30)
    print(stream.getvalue())
    return result


def main():
    args = parse_args()
    repeat = max(1, args.repeat)

    with DesktopScanner(save_outputs=not args.no_save) as scanner:
        results = []
        for _ in range(repeat):
            results.append(
                run_profiled(scanner) if args.profile else scanner.scan()
            )

    if repeat > 1:
        totals = [result["timings_ms"]["total_ms"] for result in results]
        captures = [result["timings_ms"]["capture_ms"] for result in results]
        print(
            f"repeat={repeat}; "
            f"capture avg={sum(captures) / repeat:.1f} ms; "
            f"total avg={sum(totals) / repeat:.1f} ms"
        )


if __name__ == "__main__":
    main()
