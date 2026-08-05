"""
electrician_detector.py — детекция «вор-электрик» для охранной системы.

Задача заказчика: вор притворяется электриком — в каске и сигнальном жилете,
с длинной изолирующей штангой (УКН — проверка напряжения на линии).
Триггер: человек в охраняемой зоне + длинная тонкая вертикальная штанга,
верх которой достигает кабельной зоны (фаза проверки напряжения — до перекусывания).

Метод (из скилла video-surveillance):
- Штанга: поиск по ФОРМЕ — тонкая вытянутая вертикальная линия с экстремальным
  aspect ratio рядом с человеком, верхняя точка входит в «кабельную зону» (полосу).
- Каска/жилет: сигнальный цвет (жёлтый/оранжевый hi-vis) в верхней части (каска)
  и на торсе (жилет). Цвет — вспомогательный признак для спецодежды (у штанг цвета
  разные и ночью смываются — по штанге работаем только по форме).
"""

import cv2
import numpy as np

# Сигнальные цвета спецодежды (HSV): жёлтый/оранжевый hi-vis
HI_VIS_RANGES = [
    ((15, 80, 120), (35, 255, 255)),    # жёлтый
    ((0, 90, 120), (15, 255, 255)),     # оранжевый
]

# Кабельная зона: верхняя полоса кадра (кабель подвешен 4-5 м, камера снизу/напротив)
# Нормализованные границы: верхние 35% кадра
CABLE_ZONE_Y_MAX = 0.35

# Минимальный aspect ratio штанги (высота/ширина) — 3-4 м труба на 640px кадре
POLE_MIN_ASPECT = 4.0
POLE_MIN_HEIGHT_FRAC = 0.25    # штанга не короче 25% высоты кадра
POLE_MIN_PIXEL_W = 2           # не шире ~2-3 px (тонкая)
POLE_MAX_PIXEL_W = 24          # допустимая толщина (с учётом размытия)


def detect_hi_vis(frame, bbox):
    """Доля пикселей сигнального цвета (жёлтый/оранжевый) внутри бокса человека.

    Возвращает (имеется_каска, имеется_жилет, доля_сигнального_цвета).
    Каска — верхние 25% бокса, жилет — средние 40-70%.
    """
    x1, y1, x2, y2 = [int(v) for v in bbox]
    h = y2 - y1
    if h < 20:
        return False, False, 0.0

    roi = frame[max(0, y1):y2, max(0, x1):x2]
    if roi.size == 0:
        return False, False, 0.0

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for low, high in HI_VIS_RANGES:
        mask |= cv2.inRange(hsv, np.array(low), np.array(high))

    total = mask.size
    frac = float(mask.sum()) / total if total else 0.0

    # Каска: верхние 25%
    head = mask[:max(1, int(h * 0.25))]
    head_frac = float(head.sum()) / head.size if head.size else 0.0
    # Жилет: полоса 40-70% высоты (торс)
    vest = mask[int(h * 0.40):int(h * 0.70)]
    vest_frac = float(vest.sum()) / vest.size if vest.size else 0.0

    has_helmet = head_frac > 0.08
    has_vest = vest_frac > 0.05
    return has_helmet, has_vest, frac


def find_pole(frame, person_bbox, cable_zone_y=0.35, debug=False):
    """Поиск штанги УКН по форме рядом с человеком.

    Критерии (форма, НЕ цвет):
    1. Тонкая вертикальная линия с aspect ratio >= POLE_MIN_ASPECT
    2. Высота >= POLE_MIN_HEIGHT_FRAC кадра
    3. Начинается вблизи бокса человека (рядом/в руках)
    4. Верхняя точка входит в кабельную зону (y < cable_zone_y)

    Возвращает (найдена_штанга, точки_штанги, верх_в_кабельной_зоне).
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in person_bbox]

    # Расширенная зона поиска: вокруг человека (слева/справа на ширину 1.5 бокса)
    search_x1 = max(0, x1 - int((x2 - x1) * 1.5))
    search_x2 = min(w, x2 + int((x2 - x1) * 1.5))
    search_y1 = max(0, y1 - int((y2 - y1) * 0.4))
    search_y2 = min(h, y2 + int((y2 - y1) * 0.2))

    gray = cv2.cvtColor(frame[search_y1:search_y2, search_x1:search_x2], cv2.COLOR_BGR2GRAY)
    # Штанга — тонкая вертикальная линия: морфологическое открытие вертикальным ядром
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
    opened = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)
    # Контраст с фоном
    _, thresh = cv2.threshold(opened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    poles = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if ch < POLE_MIN_HEIGHT_FRAC * h:
            continue
        if cw < POLE_MIN_PIXEL_W or cw > POLE_MAX_PIXEL_W:
            continue
        aspect = ch / max(1, cw)
        if aspect < POLE_MIN_ASPECT:
            continue
        # абсолютные координаты
        abs_x1 = search_x1 + x
        abs_y1 = search_y1 + y
        abs_x2 = search_x1 + x + cw
        abs_y2 = search_y1 + y + ch
        # верх в кабельной зоне?
        top_in_cable = abs_y1 / h < cable_zone_y
        poles.append({
            "box": (abs_x1, abs_y1, abs_x2, abs_y2),
            "aspect": aspect,
            "top_in_cable": top_in_cable,
        })

    if not poles:
        return False, [], False

    best = max(poles, key=lambda p: p["aspect"])
    return True, [best["box"]], best["top_in_cable"]


def analyze_frame(frame, detections, cable_zone_y=CABLE_ZONE_Y_MAX, debug=False):
    """Полный анализ кадра: person-детекции + проверка «вор-электрик».

    detections: список (x1,y1,x2,y2,label,conf) от YOLO.
    Возвращает список сработавших правил:
      [{"type": "electrician_thief", "person_box": ..., "helmet": bool,
        "vest": bool, "pole": bool, "pole_in_cable": bool, "confidence": float}, ...]
    """
    h, w = frame.shape[:2]
    alerts = []

    persons = [d for d in detections if d[4] == "person"]
    for p in persons:
        x1, y1, x2, y2, label, conf = p
        helmet, vest, hi_frac = detect_hi_vis(frame, (x1, y1, x2, y2))
        pole_found, pole_boxes, pole_in_cable = find_pole(frame, (x1, y1, x2, y2), cable_zone_y, debug)

        # Порог срабатывания: человек + штанга с верхом в кабельной зоне.
        # Каска/жилет усиливают уверенность (вор притворяется электриком),
        # но НЕ обязательны (ночью цвета не видны).
        if pole_found and pole_in_cable:
            confidence = 0.5 + (0.15 if helmet else 0.0) + (0.15 if vest else 0.0) + 0.1 * min(conf, 1.0)
            alerts.append({
                "type": "electrician_thief",
                "person_box": (int(x1), int(y1), int(x2), int(y2)),
                "helmet": helmet,
                "vest": vest,
                "hi_vis_fraction": round(hi_frac, 3),
                "pole": True,
                "pole_boxes": [tuple(int(v) for v in pb) for pb in pole_boxes],
                "pole_in_cable": pole_in_cable,
                "confidence": round(min(confidence, 1.0), 2),
                "base_conf": round(conf, 2),
            })
    return alerts


def draw_alerts(frame, alerts):
    """Разметка кадра: человек, штанга, кабельная зона, подписи."""
    h, w = frame.shape[:2]
    # кабельная зона
    cv2.rectangle(frame, (0, 0), (w, int(CABLE_ZONE_Y_MAX * h)), (255, 255, 0), 1)
    cv2.putText(frame, "CABLE ZONE", (5, int(CABLE_ZONE_Y_MAX * h) + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    for a in alerts:
        x1, y1, x2, y2 = a["person_box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        tags = []
        if a["helmet"]:
            tags.append("HELMET")
        if a["vest"]:
            tags.append("VEST")
        if a["pole"]:
            tags.append("POLE" + ("->CABLE" if a["pole_in_cable"] else ""))
        label = "THIEF-ELECTRICIAN " + " ".join(tags) + f" {a['confidence']:.0%}"
        cv2.putText(frame, label, (x1, max(15, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        for pb in a["pole_boxes"]:
            px1, py1, px2, py2 = pb
            cv2.rectangle(frame, (px1, py1), (px2, py2), (255, 0, 255), 2)
    return frame
