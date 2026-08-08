#!/bin/bash
# Try RTSP paths on cameras with port 554 open
cd "$LOCALAPPDATA/Temp/xfetch" || exit 1

# (ip|manufacturer_hint) pairs - guess paths by known types
declare -a IPS=(
  "176.105.214.139|Fullhan"
  "78.110.157.166|Hi3516"
  "192.173.155.111|unknown"
  "45.80.27.109|Axis"
  "175.113.15.151|unknown"
  "87.248.168.168|Hi3516"
)

for entry in "${IPS[@]}"; do
  ip="${entry%%|*}"
  hint="${entry##*|}"
  echo "===== $ip ($hint) ====="
  case "$hint" in
    Fullhan|Hi3516)
      PATHS="/live/ch0 /h264/ch1/main/av_stream /Streaming/Channels/101 /live"
      ;;
    Axis)
      PATHS="/axis-media/media.amp /onvif-media/media.amp /live /media.amp"
      ;;
    *)
      PATHS="/live/ch0 /h264/ch1/main/av_stream /Streaming/Channels/101 /axis-media/media.amp /live /onvif-media/media.amp /cam/realmonitor?channel=1&subtype=0 /videoMain /video1"
      ;;
  esac
  for p in $PATHS; do
    url="rtsp://$ip:554$p"
    out=$(timeout 6 ffprobe -v error -rtsp_transport tcp -show_entries stream=codec_name,width,height -of csv=p=0 "$url" 2>&1 | head -1)
    if [ -n "$out" ] && [ "$out" != "I/O error" ] && ! echo "$out" | grep -qE "error|Error|Unauthorized|401"; then
      echo "  ✅ $url -> $out"
    else
      echo "  ❌ $url"
    fi
  done
done
