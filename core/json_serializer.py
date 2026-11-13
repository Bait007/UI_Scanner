import json

# Сохраняет json-файл
def save_json(path: str, data: dict, pretty: bool = True) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
