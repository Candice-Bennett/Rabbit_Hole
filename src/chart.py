from __future__ import annotations

BLOCK = "█"


def bars(title: str, rows: list[tuple[str, int]], width: int = 40) -> None:
    print(f"\n--- {title} ---")
    peak = max((v for _, v in rows), default=0)
    if not peak:
        return
    label_w = max(len(label) for label, _ in rows)
    for label, v in rows:
        filled = round(v / peak * width)
        print(f"{label:<{label_w}} {BLOCK * filled}{' ' * (width - filled)} {v}")
