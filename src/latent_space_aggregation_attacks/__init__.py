"""Formal protocol v1.16 implementation."""

PROTOCOL_VERSION = "formal_protocol_v1.16"
# v1.13 deliberately retains the preregistered v1.9 sample allocation after
# the partial P0 diagnostic.  Changing this namespace would silently resample
# the pilot after outcomes had been inspected.
SEED_NAMESPACE_VERSION = "formal_protocol_v1.9"
MASTER_SEED = 205
