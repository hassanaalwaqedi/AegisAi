# AegisAI Security Guide

## API Authentication

AegisAI uses API key authentication to protect its REST endpoints.

### Configuration

1. **Set the API key** via environment variable:

```bash
export AEGIS_API_KEY="your-secret-key-here"
```

2. **Or use a `.env` file** (recommended for development):

```bash
cp .env.example .env
# Edit .env and set AEGIS_API_KEY
```

### Making Authenticated Requests

Include the API key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-secret-key" http://localhost:8080/status
```

### Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 401 | Missing or invalid API key |
| 429 | Rate limit exceeded |

---

## Rate Limiting

The API enforces rate limiting to prevent abuse:

- **Default**: 60 requests per minute per IP
- **Configurable** via environment variables:
  - `AEGIS_RATE_LIMIT`: Max requests per window
  - `AEGIS_RATE_LIMIT_WINDOW`: Window size in seconds

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AEGIS_API_KEY` | API authentication key | None (open access) |
| `AEGIS_ALLOWED_ORIGINS` | Comma-separated CORS origins | localhost only |
| `AEGIS_RATE_LIMIT` | Max requests per window | 60 |
| `AEGIS_RATE_LIMIT_WINDOW` | Rate limit window (seconds) | 60 |
| `AEGIS_DEBUG` | Enable debug mode | false |
| `AEGIS_API_HOST` | API server host | 127.0.0.1 |
| `AEGIS_API_PORT` | API server port | 8080 |

---

## Security Best Practices

1. **Always set `AEGIS_API_KEY`** in production
2. **Restrict CORS origins** to trusted domains
3. **Run behind a reverse proxy** (nginx, Caddy) for HTTPS
4. **Disable debug mode** in production (`AEGIS_DEBUG=false`)
5. **Use Docker** with non-root user (included in Dockerfile)
6. **Rotate API keys** periodically

---

## Debug Mode

When `AEGIS_DEBUG=true`:

- API docs enabled at `/docs` and `/redoc`
- Verbose logging
- Open access warnings displayed

**⚠️ Never enable debug mode in production!**

---

## Reporting Security Issues

If you discover a security vulnerability, please report it privately to the maintainers rather than opening a public issue.
