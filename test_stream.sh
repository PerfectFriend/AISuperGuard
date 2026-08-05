#!/bin/bash
# Синтетический RTSP-поток для теста (без реальных камер)
# Проверка полного цикла: поток → YOLO → тревога
ffmpeg -y -f lavfi -i "testsrc2=size=640x480:rate=10" \
  -c:v libx264 -preset ultrafast -t 60 \
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/test
