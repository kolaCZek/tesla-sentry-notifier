# Tesla Sentry Notifier
A simple application that notifies the activation of Sentry Mode in your Tesla to mqtt or ntfy.

- [https://mqtt.org](https://mqtt.org/)
- [https://ntfy.sh](https://ntfy.sh/)

## First Run - Login to Tesla Account

Create volume to persist login between container restarts.

```
docker volume create tesla-sentry-notifier
```

Run container and follow login steps (change your email address in env variable).

```
docker run -it -v tesla-sentry-notifier:/etc/tesla-sentry-notifier -e TESLA_USER="your@tesla.com" kolaczek/tesla-sentry-notifier
```

## Up-and-Running with `docker run`

```
docker run \
-d \
--rm \
--name tesla-sentry-notifier \
-v tesla-sentry-notifier:/etc/tesla-sentry-notifier \
-e TZ="YOUR_TIMEZONE" \
-e TESLA_USER="your@tesla.com" \
-e MQTT_ENABLED="true" \
-e MQTT_SERVER="127.0.0.1" \
kolaczek/tesla-sentry-notifier:latest
```

## Up-and-Running with `docker compose`

```
services:
  tesla-sentry-notifier:
    image: kolaczek/tesla-sentry-notifier:latest
    container_name: tesla-sentry-notifier
    restart: unless-stopped
    volumes:
      - tesla-sentry-notifier:/etc/tesla-sentry-notifier
    environment:
      - TZ="YOUR_TIMEZONE"
      - TESLA_USER="your@tesla.com"
      - MQTT_ENABLED="true"
      - MQTT_SERVER="127.0.0.1"
```

## Runtime Environment Variables

| Environment Variable  | Description | Default Value |
| --------------------- | ----------- | ------------- |
| `LOG_LEVEL` | STDOUT Log level | `INFO` |
| `TZ` | Time Zone Identifier | `UTC` |
| `TESLA_USER` | Login E-mail to Tesla Account | - |
| `TIMER` | Interval to check Sentry Mode status (seconds) | `10` |
| `MQTT_ENABLED` | Enable MQTT Functionality | `false` |
| `MQTT_SERVER` | MQTT Server address (ip or hostname) | - |
| `MQTT_PORT` | MQTT Server port | `1883` |
| `MQTT_USER` | MQTT User (empty = no auth) | - |
| `MQTT_PASS` | MQTT Password (empty = no auth) | - |
| `MQTT_TOPIC` | MQTT Topic prefix | `tesla-sentry` |
| `NTFY_ENABLED` | Enable NTFY Functionality | `false` |
| `NTFY_SERVER` | NTFY Server | `https://ntfy.sh` |
| `NTFY_TOPIC` | NTFY Topic | - |
| `NTFY_TOKEN` | NTFY access token | - |
| `HONK_HORN` | Honk car's horn when Sentry activated (be sensible) | `false` |
| `FLASH_LIGHTS` | Flash car's lights when Sentry activated | `false` |

## Support Me

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/kolaczek)
