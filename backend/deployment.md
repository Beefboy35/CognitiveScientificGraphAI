# Backend deployment

## Production domains

- UI: https://kb.studyninja.ru, https://kb.xteam.pro
- API: https://api.kb.studyninja.ru, https://api.kb.xteam.pro

## Docker Compose

Backend is deployed as the `fastapi` service behind Traefik.

### Select environment file

```bash
ENV_FILE=.env.prod docker compose --env-file .env.prod up -d --build
```

### Required env

- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- `PG_DSN`
- `JWT_SECRET_KEY`
- `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` (first deploy)

## Post-deploy checks

- `GET /health`
- `GET /docs`

## Security notes

- Do not commit `.env.prod` with secrets.
- Rotate `JWT_SECRET_KEY` only with a planned logout window (all tokens become invalid).
