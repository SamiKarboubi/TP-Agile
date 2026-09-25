FROM node:22-bookworm-slim AS mcp

RUN npm install --global tmdb-mcp@0.11.0

FROM python:3.13-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=mcp /usr/local/bin/node /usr/local/bin/node
COPY --from=mcp /usr/local/bin/tmdb-mcp /usr/local/bin/tmdb-mcp
COPY --from=mcp /usr/local/lib/node_modules/tmdb-mcp /usr/local/lib/node_modules/tmdb-mcp
RUN node --version && test -x /usr/local/bin/tmdb-mcp

COPY app ./app

ENV TMDB_MCP_COMMAND=tmdb-mcp
ENV TMDB_MCP_ARGS=[]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
