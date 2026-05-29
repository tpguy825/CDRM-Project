FROM python:3.12-slim

EXPOSE 5000
WORKDIR /app

COPY requirements.txt main.py /app/

RUN pip install --no-cache-dir -r requirements.txt

COPY configs/ /app/configs/
COPY custom_functions/ /app/custom_functions/
COPY cdrm-frontend/ /app/cdrm-frontend/
COPY routes/ /app/routes/

CMD ["python", "main.py"]
