"""ETL loaders: one module per source, each exposing extract/transform/load.

`extract()` touches files only. `transform()` is pure -- no session, no I/O --
so it can be unit-tested without a database. `load()` is the only function
allowed to take a Session, and it is where idempotency (upsert, or a
feed_version check) lives.
"""
