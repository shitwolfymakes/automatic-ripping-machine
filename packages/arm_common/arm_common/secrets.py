"""Shared secret-masking sentinel. The single source for the `<hidden>` literal
used to mask secret values on read across config + notification-channel surfaces,
so the two can never drift."""

HIDDEN_SECRET = "<hidden>"
