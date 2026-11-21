FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-noto-core && rm -rf /var/lib/apt/lists/*
WORKDIR /studio
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py media.py engine.py demo.json README.md .env.example Dockerfile ./
COPY static ./static
ENV HOST=0.0.0.0 PORT=8787 AFTERTONE_DATA=/studio/data
EXPOSE 8787
CMD ["python","app.py"]
