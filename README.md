# quant_autoresearch

Active scratchpad for one strategy at a time.

The loop is intentionally small:

```text
strategy.py + experiment.yml -> runner.py -> quant_strategies.runner -> results/
```

During an autonomous loop, agents may edit only:

```text
strategy.py
experiment.yml
```

The harness files are fixed unless Season explicitly asks to change them.

`runner.py` converts `experiment.yml` into a temporary TOML run config and calls
`quant_strategies.runner.run_config` directly.

## Run

```bash
conda run -n quant python runner.py --max-attempts 1
```
