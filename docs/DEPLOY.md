# Despliegue

## Regla de oro: un solo proceso

El estado (cooldowns, contadores, claves en caliente) vive en memoria y se
persiste en `data/state.json`. **No uses `--workers > 1`** ni varios contenedores
sobre el mismo archivo: cada proceso tendría su propia visión de las cuotas.
Para escalar de verdad, cambia el almacén por Redis (ver
[`ARQUITECTURA.md`](ARQUITECTURA.md#ampliaciones)).

---

## 1. Docker Compose (recomendado en VPS)

```bash
git clone https://github.com/yoandryforbes776-rgb/apk2.git && cd apk2
cp .env.example .env
nano .env                     # claves + ROUTER_TOKEN + ADMIN_TOKEN
docker compose up -d --build
docker compose logs -f
curl -s localhost:8080/health
```

Actualizar:

```bash
git pull
docker compose up -d --build
```

Los datos quedan en `./data` y la configuración en `./config`.

---

## 2. systemd (Python directo)

`/etc/systemd/system/free-ai-router.service`:

```ini
[Unit]
Description=Free AI Router
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=router
Group=router
WorkingDirectory=/opt/apk2
EnvironmentFile=/opt/apk2/.env
ExecStart=/opt/apk2/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --proxy-headers
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/apk2/data
UMask=0077

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd -r -s /usr/sbin/nologin router
sudo mkdir -p /opt/apk2 && sudo chown -R router:router /opt/apk2
sudo -u router python3 -m venv /opt/apk2/.venv
sudo -u router /opt/apk2/.venv/bin/pip install -r /opt/apk2/requirements.txt
sudo systemctl enable --now free-ai-router
sudo journalctl -u free-ai-router -f
```

Con `--host 127.0.0.1`, solo el proxy inverso puede acceder: perfecto.

---

## 3. HTTPS con Caddy

`/etc/caddy/Caddyfile`:

```caddyfile
ai.tudominio.com {
    encode zstd gzip

    # Opción A: el router ya exige ROUTER_TOKEN (recomendado)
    reverse_proxy 127.0.0.1:8080 {
        flush_interval -1          # imprescindible para SSE
        transport http {
            read_timeout 300s
        }
    }

    # Opción B: además, autenticación básica para la consola web
    # (la APK usaría el token del router, no basic auth)
    @ui path / /ui/* /admin/*
    basicauth @ui {
        admin $2a$14$REEMPLAZA_ESTE_HASH
    }

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "no-referrer"
    }
}
```

Genera el hash con `caddy hash-password --plaintext 'tu-clave'`.

**Alternativa nginx**:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_buffering off;          # streaming
    proxy_read_timeout 300s;
}
```

---

## 4. Cloudflare Tunnel (sin abrir puertos)

```bash
cloudflared tunnel login
cloudflared tunnel create ai-router
cloudflared tunnel route dns ai-router ai.tudominio.com
cloudflared tunnel run --url http://127.0.0.1:8080 ai-router
```

Ventajas: TLS automático, no expones IP. Añade `ADMIN_TOKEN` **antes** de
publicar nada y considera Cloudflare Access para `/admin/*`.

---

## 5. Termux (router dentro del Android)

```bash
bash scripts/termux-setup.sh
source .venv/bin/activate
termux-wake-lock
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Arranque automático al encender con [Termux:Boot](https://wiki.termux.com/wiki/Termux:Boot):
crea `~/.termux/boot/router.sh`:

```bash
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
cd ~/apk2
. .venv/bin/activate
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 >> ~/apk2/router.log 2>&1 &
```

```bash
chmod +x ~/.termux/boot/router.sh
```

Y en Ajustes de Android: batería → sin restricciones para Termux.

---

## 6. Comprobaciones tras el despliegue

```bash
curl -s https://ai.tudominio.com/health | jq
curl -s https://ai.tudominio.com/v1/models -H "Authorization: Bearer $ROUTER_TOKEN" | jq '.data[0:3]'
curl -sN https://ai.tudominio.com/v1/chat/completions \
  -H "Authorization: Bearer $ROUTER_TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"auto","stream":true,"messages":[{"role":"user","content":"ping"}]}'
```

El streaming debe llegar **progresivamente**. Si llega de golpe, el proxy está
bufferizando: revisa `flush_interval -1` (Caddy) o `proxy_buffering off` (nginx).

---

## 7. Copias y mantenimiento

```bash
# Qué guardar: .env + data/state.json (+ config/providers.json si lo editas)
tar czf backup-router-$(date +%F).tgz .env data/state.json config/providers.json
chmod 600 backup-router-*.tgz
```

- Rota claves cada cierto tiempo y revoca las que ya no uses.
- Revisa `/admin/status` para detectar claves muertas (`disabled`).
- `python scripts/doctor.py --ping` desde cron semanal avisa de proveedores caídos:

```cron
0 9 * * 1 cd /opt/apk2 && .venv/bin/python scripts/doctor.py --ping >/var/log/router-doctor.log 2>&1
```

---

## 8. Checklist de seguridad

- [ ] `ROUTER_TOKEN` largo y aleatorio (`openssl rand -hex 32`).
- [ ] `ADMIN_TOKEN` distinto y también aleatorio.
- [ ] `/admin/*` no accesible desde Internet sin token ni basic auth.
- [ ] HTTPS terminado en Caddy/Cloudflare/nginx.
- [ ] `chmod 600 .env data/state.json` (el router ya escribe `state.json` en 600).
- [ ] Firewall: solo 80/443 públicos; 8080 en loopback.
- [ ] Uso razonable: no revender ni automatizar abuso de free tiers.
- [ ] `.env` **nunca** en Git (ya está en `.gitignore`).
