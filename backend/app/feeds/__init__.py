"""Life-data feeds: weather (Open-Meteo archive), calendar (ICS mirror),
Home Assistant history. Every feed is a pure-pull idempotent sync and is
safe to call repeatedly — rows UPSERT on their natural key.

None of these feeds go anywhere near Garmin.
"""
