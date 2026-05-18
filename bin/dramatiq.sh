#!/bin/bash

PROCESSES=2
THREADS_PER_PROCESS=2

git rev-parse HEAD > etc/version
echo "Starting Dramatiq for Noon Scrapper in Mode $MODE"

#sleep infinity
if [ "$MODE" = "DEVELOPMENT" ]; then
    echo "Starting with Remote Debugging capability.."
    python manage.py rundramatiq --reload  --processes $PROCESSES --threads $THREADS_PER_PROCESS
else
    echo "Starting in $MODE Mode.."
    python manage.py rundramatiq --processes $PROCESSES --threads $THREADS_PER_PROCESS
fi
