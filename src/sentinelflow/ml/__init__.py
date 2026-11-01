# =============================================================================
# SentinelFlow - Machine Learning (ADR 0003)
# =============================================================================
"""
One supervised fraud model, trained offline and served by the API and detector.

Subpackages (imported on demand, nothing heavy at package import):

- ``sentinelflow.ml.samld_dataset``: SAML-D canonical dataset and time split (ML-02)
- ``sentinelflow.ml.features``: feature set ``fs-1``, batch and streaming (ML-03)
- ``sentinelflow.ml.training``: training, locked-test evaluation, artifact (ML-04/05)
- ``sentinelflow.ml.serving``: artifact loader, model service, scorer (ML-06)
- ``sentinelflow.ml.ci``: ML Pipeline workflow helpers (ML-07)

The earlier ensemble, GNN, temporal and federated code is out of scope (ADR 0003
§1) and was removed in ML-08; it is kept at the ``archive/ml-legacy-s4`` tag.
"""
