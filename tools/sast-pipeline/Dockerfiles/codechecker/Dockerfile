FROM ubuntu:22.04


RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make cmake zlib1g-dev python3-dev curl git jq python3-pip\
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*


RUN pip3 install --no-cache-dir codechecker tqdm orjson


WORKDIR /workspace
COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]
