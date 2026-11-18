FROM sast-builder-runtime-test:verification
COPY tests/fixtures/build_runtime/source_analyzer.py /test/source_analyzer.py
ENTRYPOINT ["python3", "/test/source_analyzer.py"]
