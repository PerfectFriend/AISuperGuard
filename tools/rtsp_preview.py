"""
rtsp_preview.py — просмотр RTSP-потока (проверка камеры перед запуском охраны).

Запуск:
  python tools/rtsp_preview.py rtsp://user:pass@IP:554/stream1
  python tools/rtsp_preview.py rtsp://... --save preview.jpg   # сохранить кадр
"""

import argparse
import sys
import time

import cv2


def main():
    ap = argparse.ArgumentParser(description="Просмотр RTSP-потока")
    ap.add_argument("url", help="RTSP URL")
    ap.add_argument("--save", default=None, help="сохранить один кадр в файл")
    ap.add_argument("--seconds", type=float, default=5, help="сколько смотреть, сек")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print(f"❌ Не удалось открыть: {args.url}")
        print("   Проверь: IP, порт, логин/пароль, путь потока (см. docs/CAMERA-SETUP.md)")
        sys.exit(1)

    print(f"✅ Поток открыт: {args.url}")
    print(f"   Размер: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")

    start = time.time()
    frames = 0
    while time.time() - start < args.seconds:
        ok, frame = cap.read()
        if not ok:
            print("⚠️ Потеря кадра...")
            time.sleep(0.5)
            continue
        frames += 1
        if frames == 1 and args.save:
            cv2.imwrite(args.save, frame)
            print(f"💾 Кадр сохранён: {args.save}")

        cv2.imshow("Camera", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print(f"✅ Просмотрено {frames} кадров за {time.time()-start:.1f}с. "
          f"≈{frames/max(0.1, time.time()-start):.0f} fps")


if __name__ == "__main__":
    main()
