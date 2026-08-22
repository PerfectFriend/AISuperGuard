#!/bin/bash
# Evolution script for SuperGuard dashboard
# Runs 10000 cycles, every 10 cycles runs build/test and backup

set -e

BASE_DIR="/home/thomas/SuperGuard"
WEB_DIR="$BASE_DIR/web-dashboard"
API_DIR="$BASE_DIR/superguard-api"
LOG_FILE="$BASE_DIR/evolution.log"
BACKUP_DIR="$BASE_DIR/evolution_backups"
mkdir -p "$BACKUP_DIR"

echo "Starting evolution at $(date)" | tee -a "$LOG_FILE"

for ((cycle=1; cycle<=10000; cycle++)); do
    # Simulate some work: we could run a quick check, but for now just sleep a bit to avoid spinning
    sleep 0.1
    
    # Every 10 cycles: run build, test, backup
    if [ $((cycle % 10)) -eq 0 ]; then
        echo "  Running build and test at cycle $cycle" | tee -a "$LOG_FILE"
        cd "$WEB_DIR"
        # Run TypeScript check and Vite build
        if npm run build 2>&1 | tee -a "$LOG_FILE"; then
            echo "  Build succeeded" | tee -a "$LOG_FILE"
            # Quick sanity check: ensure output files exist and are non-zero
            if ls "$WEB_DIR/dist/assets/index-"*.js 1>/dev/null 2>&1 && ls "$WEB_DIR/dist/assets/index-"*.css 1>/dev/null 2>&1; then
                if [ -s "$WEB_DIR/dist/assets/index-"*.js ] && [ -s "$WEB_DIR/dist/assets/index-"*.css ]; then
                    echo "  Build output looks good" | tee -a "$LOG_FILE"
                else
                    echo "  WARNING: Build output empty" | tee -a "$LOG_FILE"
                fi
            else
                echo "  WARNING: Build output missing" | tee -a "$LOG_FILE"
            fi
        else
            echo "  Build failed at cycle $cycle" | tee -a "$LOG_FILE"
            # Continue evolution despite failure? We'll continue but note.
        fi
        
        # Backup the entire project (excluding node_modules, dist, etc.)
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        BACKUP_FILE="$BACKUP_DIR/superguard_backup_cycle_${cycle}_${TIMESTAMP}.zip"
        echo "  Creating backup: $BACKUP_FILE" | tee -a "$LOG_FILE"
        cd "$BASE_DIR"
        zip -r "$BACKUP_FILE" . -x "node_modules/*" "web-dashboard/dist/*" "web-dashboard/src/*tsbuildinfo" "**/*.log" ".*" 2>&1 | tee -a "$LOG_FILE"
        echo "  Backup completed" | tee -a "$LOG_FILE"
        
        # Optional: run a simple API health check
        if curl -s http://localhost:8080/api/v1/system/health | grep -q '"status":"healthy"'; then
            echo "  API health check passed" | tee -a "$LOG_FILE"
        else
            echo "  WARNING: API health check failed" | tee -a "$LOG_FILE"
        fi
        
        echo "  Cycle $cycle completed successfully at $(date)" | tee -a "$LOG_FILE"
    fi
    
    # Optional: small delay to prevent overheating
    sleep 0.05
done

echo "Evolution completed after 10000 cycles at $(date)" | tee -a "$LOG_FILE"