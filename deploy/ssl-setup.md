# SSL Certificate Setup Guide

This guide covers SSL certificate setup for AegisAI HTTPS deployment.

---

## Quick Start (Development - Self-Signed)

Generate self-signed certificates for local development:

```bash
cd deploy

# Create ssl directory
mkdir -p ssl

# Generate self-signed certificate (valid 365 days)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/aegis.key \
  -out ssl/aegis.crt \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
```

> **Note**: Self-signed certificates will show browser warnings. Only use for development.

---

## Production (Let's Encrypt)

### Prerequisites
- Domain name pointing to your server
- Ports 80 and 443 accessible

### Using Certbot

```bash
# Install certbot
apt-get update && apt-get install certbot

# Stop nginx temporarily
docker-compose stop nginx

# Obtain certificate
certbot certonly --standalone -d yourdomain.com

# Copy certificates
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem deploy/ssl/aegis.crt
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem deploy/ssl/aegis.key

# Restart nginx
docker-compose up -d nginx
```

### Auto-Renewal

Add to crontab:

```bash
0 0 1 * * certbot renew --quiet && docker-compose restart nginx
```

---

## Docker Compose with Certbot

Alternative setup using certbot container:

```yaml
# Add to docker-compose.yml
certbot:
  image: certbot/certbot
  volumes:
    - ./ssl:/etc/letsencrypt
    - ./certbot-www:/var/www/certbot
  entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
```

---

## Verify SSL

After setup, verify your certificate:

```bash
# Check certificate details
openssl x509 -in deploy/ssl/aegis.crt -text -noout

# Test HTTPS connection
curl -v https://localhost --insecure

# Online SSL test (production only)
# https://www.ssllabs.com/ssltest/
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Certificate not trusted" | Self-signed cert, expected in dev |
| "Connection refused" | Check nginx is running, ports open |
| "Certificate expired" | Renew with certbot |
| Permission denied | Check file permissions on ssl/ |

---

## Security Best Practices

1. **Never commit** SSL private keys to git
2. **Add ssl/ to .gitignore** (already done)
3. **Rotate certificates** before expiry
4. **Use strong ciphers** (configured in nginx.conf)
5. **Enable HSTS** (configured in nginx.conf)
