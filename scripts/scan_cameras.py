"""
scan_cameras.py — поиск IP-камер в локальной сети.

Находит камеры по открытым портам (554=RTSP, 80/8080=web, 8000/37777=Dahua/XMeye),
пытается угадать производителя и выдаёт готовый RTSP URL для конфига.

Запуск:
  python scan_cameras.py                          # автоопределение подсети
  python scan_cameras.py --subnet 192.168.1.0/24  # конкретная подсеть
  python scan_cameras.py --ports 554,80,8080      # свои порты
"""

import argparse
import ipaddress
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Порты, характерные для IP-камер
CAMERA_PORTS = {
    554: "RTSP",
    80: "HTTP/web",
    8000: "Hikvision SDK",
    8080: "HTTP-alt",
    37777: "Dahua/XMeye",
    34567: "XiongMai",
    9000: "Dahua RTSP-alt",
    8899: "Hikvision ISAPI",
}

RTSP_PATHS = {
    "hikvision": ["/Streaming/Channels/101", "/stream1"],
    "dahua": ["/cam/realmonitor?channel=1&subtype=0", "/live", "/stream1"],
    "uniview": ["/unicast/c1/s0/live", "/live"],
    "generic": ["/stream1", "/live", "/ch0", "/h264", "/videoMain"],
}


def detect_producer(open_ports, banners):
    """Угадывание производителя по портам и HTTP-баннерам."""
    blob = " ".join(banners).lower()
    if "dahua" in blob or 37777 in open_ports:
        return "dahua"
    if "hikvision" in blob or 8000 in open_ports or 8899 in open_ports:
        return "hikvision"
    if "uniview" in blob:
        return "uniview"
    if 554 in open_ports:
        return "generic"
    return "unknown"


def check_host(ip, ports):
    """Проверка одного хоста: какие камерные порты открыты."""
    open_ports = {}
    for port in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.8)
            if s.connect_ex((str(ip), port)) == 0:
                open_ports[port] = True
            s.close()
        except Exception:
            pass
    return open_ports


def http_banner(ip, port=80, timeout=2):
    """Пытается получить HTTP-заголовок сервера (для определения производителя)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((str(ip), port))
        s.sendall(b"GET / HTTP/1.0\r\nHost: x\r\n\r\n")
        data = s.recv(2048).decode("utf-8", errors="ignore")
        s.close()
        return data
    except Exception:
        return ""


def auto_subnet():
    """Автоопределение подсети по IP машины."""
    try:
        out = subprocess.run(["ipconfig"], capture_output=True, text=True,
                             timeout=10).stdout
        import re
        m = re.search(r"IPv4.*?(\d+\.\d+\.\d+\.\d+)", out)
        if m:
            ip = m.group(1)
            parts = ip.split(".")
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except Exception:
        pass
    return "192.168.1.0/24"


def main():
    ap = argparse.ArgumentParser(description="Поиск IP-камер в сети")
    ap.add_argument("--subnet", default=None, help="подсеть, напр. 192.168.1.0/24")
    ap.add_argument("--ports", default="554,80,8080,8000,37777",
                    help="порты через запятую")
    ap.add_argument("--timeout", type=float, default=0.8, help="таймаут на хост, сек")
    args = ap.parse_args()

    subnet = args.subnet or auto_subnet()
    ports = [int(p) for p in args.ports.split(",") if p.strip()]
    network = ipaddress.ip_network(subnet, strict=False)
    hosts = list(network.hosts())

    print(f"🔍 Сканирую {subnet} ({len(hosts)} хостов), порты: {args.ports}")
    print("   Это может занять 1-3 минуты...\n")

    found = []

    def worker(ip):
        open_ports = check_host(ip, ports)
        if not open_ports:
            return None
        banners = []
        if 80 in open_ports:
            banners.append(http_banner(ip, 80))
        if 8080 in open_ports:
            banners.append(http_banner(ip, 8080))
        producer = detect_producer(list(open_ports.keys()), banners)
        return {"ip": str(ip), "ports": list(open_ports.keys()), "producer": producer}

    with ThreadPoolExecutor(max_workers=64) as ex:
        futs = [ex.submit(worker, ip) for ip in hosts]
        for fut in as_completed(futs):
            res = fut.result()
            if res:
                found.append(res)
                tag = "📷" if res["producer"] != "unknown" else "❓"
                print(f"  {tag} {res['ip']}  порты={res['ports']}  "
                      f"производитель={res['producer']}")

    print(f"\n{'='*60}")
    if not found:
        print("❌ Камеры не найдены. Проверь: камера включена? в одной подсети?")
        print("   Попробуй: python scan_cameras.py --subnet 192.168.0.0/24")
        return

    print(f"✅ Найдено устройств с камерными портами: {len(found)}\n")
    print("Готовые RTSP-URL (подставь логин/пароль камеры):")
    for f in found:
        producer = f["producer"]
        paths = RTSP_PATHS.get(producer, RTSP_PATHS["generic"])
        for p in paths:
            print(f"  rtsp://user:pass@{f['ip']}:554{p}   [{producer}]")
    print("\n💡 Логин/пароль камеры обычно на наклейке снизу или стандартный (admin/admin).")


if __name__ == "__main__":
    main()
