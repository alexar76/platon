FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY platon ./platon
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "numpy>=2.1.0" \
    "httpx>=0.27.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings>=2.6.0" \
    "python-dateutil>=2.9.0" \
    "cryptography>=44.0.0"
ENV PYTHONPATH=/app
# One numpy/OpenBLAS thread — avoids one uvicorn process saturating all cores.
ENV OPENBLAS_NUM_THREADS=1
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1
EXPOSE 9200
# Explicit single worker — never spawn a multi-process pool by accident.
CMD ["python", "-m", "uvicorn", "platon.main:app", "--host", "0.0.0.0", "--port", "9200", "--workers", "1"]
