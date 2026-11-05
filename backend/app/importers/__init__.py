"""Offline importers for bulk-exported activity files.

No importer makes a network call. Each walks a local directory tree or ZIP
archive, parses what it finds, and inserts rows into the same schema the
live sync uses. Dedup against existing activities is by start_time±60s +
similar distance + similar duration; keeps the earliest-inserted row.
"""
