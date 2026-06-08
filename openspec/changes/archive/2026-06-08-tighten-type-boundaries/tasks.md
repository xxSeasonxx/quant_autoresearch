## 1. Mypy Configuration

- [x] 1.1 Add narrow mypy configuration for `quant_strategies.*` untyped imports.
- [x] 1.2 Verify no broad missing-import ignore is introduced.

## 2. Strategy Type Boundary

- [x] 2.1 Add a numeric param value alias in `strategy.py`.
- [x] 2.2 Make `_DEFAULTS` and `validate_params()` return type precise.
- [x] 2.3 Replace direct object-to-int/float conversions with small typed coercion helpers.
- [x] 2.4 Preserve existing strategy behavior covered by tests.

## 3. Test Type Boundary

- [x] 3.1 Add targeted casts in `tests/test_protocol.py` for nested quick-run config sections.
- [x] 3.2 Avoid weakening production types to satisfy tests.

## 4. Docs And Verification

- [x] 4.1 Mark foundation review P3 item addressed after mypy passes.
- [x] 4.2 Run `conda run -n quant python -m mypy .`.
- [x] 4.3 Run `conda run -n quant python -m pytest -q`.
- [x] 4.4 Run `conda run -n quant python -m ruff check .`.
- [x] 4.5 Run `openspec validate tighten-type-boundaries --strict`.
- [x] 4.6 Run `conda run -n quant python -m loop status`.
