# ECHO conversation model on Hugging Face: Ollama 0.30.11 with the llama3.2:3b build ECHO's prompt screen used.
# Run it as a private Docker Space on paid hardware with a short sleep time; the ECHO Space wakes it when needed.
FROM ollama/ollama:0.30.11@sha256:c484b703176aa19dfc0a54cbfb60ab8094b38faa04283fb77eba1d33319e5eca

# The model is baked into the image, so a wake-up loads it from local disk instead of downloading 2 GB.
# The build fails unless the pulled model is build a80c4f17acd5.
ENV OLLAMA_MODELS=/models
RUN mkdir -p /models \
 && (ollama serve >/tmp/ollama-build.log 2>&1 &) \
 && for i in $(seq 1 60); do ollama list >/dev/null 2>&1 && break; sleep 1; done \
 && ollama pull llama3.2:3b \
 && ollama list | grep -Eq '^llama3\.2:3b[[:space:]]+a80c4f17acd5' \
 && chmod -R a+rX /models

COPY start.sh /start.sh
# Hugging Face runs the container as user 1000: keep Ollama's home writable and serve on the Space port.
ENV HOME=/tmp/ollama-home OLLAMA_HOST=0.0.0.0:7860 OLLAMA_KEEP_ALIVE=-1
EXPOSE 7860
ENTRYPOINT ["/bin/sh", "/start.sh"]
