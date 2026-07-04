FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Default: launch the dashboard. Override CMD to run `python main.py --target ...`
# or `python -m mcp_server.server` instead.
CMD ["streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0"]
