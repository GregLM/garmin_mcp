#!/bin/sh
set -e

# Reconstruit les tokens Garmin depuis une variable d'environnement,
# car le plan gratuit Render n'a pas de disque persistant.
if [ -n "$GARMIN_TOKENS_B64" ]; then
    mkdir -p /root/.garminconnect
    echo "$GARMIN_TOKENS_B64" | base64 -d > /root/.garminconnect/garmin_tokens.json
    chmod 600 /root/.garminconnect/garmin_tokens.json
fi

# Render assigne le port d'écoute via $PORT ; on le transmet au serveur.
if [ -n "$PORT" ]; then
    export GARMIN_MCP_PORT="$PORT"
fi

exec garmin-mcp