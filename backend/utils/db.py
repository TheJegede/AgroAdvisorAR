def _assert_insert(result, label: str) -> None:
    if not result.data:
        raise RuntimeError(f"{label} insert returned no data")
