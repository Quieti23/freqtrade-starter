FROM freqtradeorg/freqtrade:2026.1@sha256:320a43dcea1229878163af6008c4118d2f062ca13db6aa3d4a5f51bbcbedf298

USER root
# Upstream keeps Python user packages behind a 0700 home directory.
RUN chmod o+rx /home/ftuser
USER ftuser
