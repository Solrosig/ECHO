---
title: ECHO conversation model
emoji: 💬
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: llama3.2
---

# ECHO conversation model

Ollama 0.30.11 serving `llama3.2:3b`, build `a80c4f17acd5` (Q4_K_M): the model and build ECHO's conversation prompt was tested with. The image does not build with any other build.

- Keep this Space **private**. The ECHO Space calls it with a token that can only read this Space, stored as its secret `ECHO_OLLAMA_TOKEN`.
- Run it on paid hardware with a short sleep time. The ECHO website wakes it when someone opens Explore, and Hugging Face bills only while it is starting or awake.
- Ollama keeps no conversations: each request is answered and nothing is written to disk.
- Set up with `../huggingface/configure_space.py b` from the ECHO repository.

Built with Llama. Llama 3.2 is licensed under the Llama 3.2 Community License, Copyright © Meta Platforms, Inc. All Rights Reserved. Licence: https://www.llama.com/llama3_2/license/