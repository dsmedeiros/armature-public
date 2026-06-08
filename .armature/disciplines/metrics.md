---
id: metrics
severity: standard
composition-mode: advisory
---

# Metrics

## When to apply

Apply when adding or modifying instrumentation, observability, or monitoring code.
Triggered by paths matching `**/metrics*`, `**/telemetry*`, `**/observability*`.

## Standards

1. **Choose a measurement framework and apply it consistently.** For request-serving
   systems use RED (Rate, Errors, Duration). For resource-managing systems use USE
   (Utilization, Saturation, Errors). Document which framework applies to each service
   in the service's runbook.

2. **Cardinality limits: no user-generated values in label sets.** High-cardinality
   labels (user IDs, tenant IDs, request IDs) explode Prometheus memory and break
   dashboards. Permitted label values must be bounded and enumerable. Example violation:
   `http_requests_total{user_id="u-29fa3b"}` — user_id is unbounded, forbidden.
   Correct: `http_requests_total{endpoint="/api/v1/orders", status="200"}`.

3. **Naming conventions: snake_case, meaningful suffixes.**
   - Counters: `_total` suffix — `http_requests_total`, `cache_misses_total`
   - Histograms: `_seconds` for time, `_bytes` for size — `request_duration_seconds`
   - Gauges: no suffix — `active_connections`, `queue_depth`
   - Never use abbreviations: `req` not accepted, `request` required.

4. **Histogram vs. gauge selection.**
   - Histogram: measurable distributions where you want percentiles (latency, request size).
     Use `observe()` per event.
   - Gauge: current point-in-time value (queue depth, active connections, memory usage).
     Use `set()` or `inc()`/`dec()`.
   - Mistake: using a gauge for latency (loses distribution information).

5. **Every new metric requires a Grafana dashboard panel or runbook entry.** An unplotted
   metric is wasted instrumentation. Before merging, confirm the metric appears in an
   existing or new dashboard panel and has an alert rule if it is SLO-relevant.

## Cross-references

- ARMATURE.md §3 (agent behavioral rules)
- `data-handling.md` (never include PII in metric labels)
- `error-handling.md` (error metrics must be emitted on exception paths)
