FROM jetbrains/qodana-jvm-community:2025.2

WORKDIR /workspace
COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh
COPY qodana.yaml /data/qodana.yaml

ENTRYPOINT ["/analyze.sh"]
