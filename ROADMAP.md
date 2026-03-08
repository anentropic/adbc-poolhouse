# Roadmap

- async support
  - ADBC interface spec is inherently sync, this is likely more a requirement for downstream code to run ADBC calls in a separate thread using `loop.run_in_executor`
