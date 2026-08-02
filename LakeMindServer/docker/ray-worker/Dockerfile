FROM rayproject/ray:2.41.0-py312

USER root
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    torch torchaudio --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    funasr==1.3.29 \
    librosa \
    fastembed \
    httpx

USER ray
