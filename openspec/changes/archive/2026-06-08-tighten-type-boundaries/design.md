## Context

Current mypy failures:

- untyped `quant_strategies.*` imports;
- loose `object` values in `strategy.py` params;
- tests indexing nested dicts typed as `object`.

The root fix is to make local boundaries typed and explicitly scope the upstream typing limitation.

## Goals / Non-Goals

**Goals:**

- Make `conda run -n quant python -m mypy .` pass.
- Keep runtime behavior unchanged.
- Avoid broad ignore settings.

**Non-Goals:**

- Do not modify `quant_strategies`.
- Do not add vendored stubs.
- Do not refactor strategy logic beyond local type coercion.

## Decisions

- Add `[[tool.mypy.overrides]] module = ["quant_strategies.*"] ignore_missing_imports = true`.
- Keep `validate_params(params: Mapping[str, object])` as the strategy boundary but return a typed `dict[str, int | float]`.
- Use small numeric coercion helpers in `strategy.py` instead of direct `int(object)` / `float(object)` calls.
- Use targeted casts in tests rather than weakening production types.

## Risks / Trade-offs

- **Untyped upstream imports remain unchecked** -> The override is explicit and limited to `quant_strategies.*`.
- **Strategy string params may no longer be accepted** -> Ordinary params come from validated TOML numeric values; preserving string coercion is not needed for this local strategy contract.
