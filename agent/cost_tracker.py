MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5": (3.75, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-haiku-3.5": (0.80, 4.00),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
}
# USD per 1M tokens (input, output)


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    # Sort by prefix length descending to avoid short-prefix collisions
    # (e.g. "gpt-4o" matching "gpt-4o-mini" before the longer prefix).
    for prefix in sorted(MODEL_PRICES, key=len, reverse=True):
        in_price, out_price = MODEL_PRICES[prefix]
        if model.startswith(prefix):
            return (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price
    return None


def format_cost(cost: float | None) -> str:
    if cost is None:
        return "unknown"
    if cost < 0.01:
        return f"${cost:.6f}"
    return f"${cost:.4f}"
