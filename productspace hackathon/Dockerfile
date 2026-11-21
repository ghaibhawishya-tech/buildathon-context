FROM node:22-bookworm-slim AS youtube-runtime
FROM python:3.12-slim-bookworm
COPY --from=youtube-runtime /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends curl libstdc++6 fonts-dejavu-core fonts-noto-core && rm -rf /var/lib/apt/lists/*
WORKDIR /studio
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py chat.py kinetic.py narration.py sources.py editor.py speech.py media.py engine.py demo.json brief.json README.md .env.example Dockerfile ./
RUN printf ".runtime\ndata\n.venv\n.env\n__pycache__\n*.zip\n" > .dockerignore
COPY motion ./motion
COPY static ./static
RUN python motion/film.py exports/cinematic_video.mp4 && python motion/film.py --portrait exports/aftertone_short.mp4 && python motion/studio_cut.py
ENV HOST=0.0.0.0 PORT=8787 AFTERTONE_DATA=/studio/data
EXPOSE 8787
CMD ["python","app.py"]
