#!/bin/sh
set -e

# 1. Récupère les jetons Garmin les plus récents :
#    d'abord dans Supabase, sinon dans la variable GARMIN_TOKENS_B64 (secours).
#    (Le plan gratuit Render n'a pas de disque persistant.)
python /app/token_sync.py pull

# 2. Surveillance en arrière-plan : chaque jeton renouvelé par la
#    bibliothèque Garmin est recopié dans Supabase.
python /app/token_sync.py watch &

# Render assigne le port d'écoute via $PORT ; on le transmet au serveur.
if [ -n "$PORT" ]; then
    export GARMIN_MCP_PORT="$PORT"
fi

exec garmin-mcp
