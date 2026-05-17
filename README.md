# quant_autoresearch

Active scratchpad for one strategy at a time.

The loop is intentionally small:

```text
strategy.py + experiment.yml -> runner.py -> quant_engine -> results/
```

During an autonomous loop, agents may edit only:

```text
strategy.py
experiment.yml
```

The harness files are fixed unless Season explicitly asks to change them.

## Run

```bash
conda run -n quant python runner.py --max-attempts 1
```
