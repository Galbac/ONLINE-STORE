from datetime import datetime, time
from typing import Any

from source.config.settings import settings

DAY_NAMES: dict[int, str] = {
    1: "Понедельник",
    2: "Вторник",
    3: "Среда",
    4: "Четверг",
    5: "Пятница",
    6: "Суббота",
    7: "Воскресенье",
}

SHORT_DAY_NAMES: dict[int, str] = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
    7: "Вс",
}


def get_default_schedule() -> list[dict[str, Any]]:
    return [
        {
            "day": day_num,
            "day_name": DAY_NAMES[day_num],
            "is_day_off": False,
            "open_time": "08:00",
            "close_time": "22:00",
        }
        for day_num in range(1, 8)
    ]


def normalize_schedule(schedule: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not schedule:
        return get_default_schedule()

    schedule_by_day = {item.get("day"): item for item in schedule if isinstance(item, dict) and item.get("day") in DAY_NAMES}
    normalized: list[dict[str, Any]] = []

    for day_num in range(1, 8):
        if day_num in schedule_by_day:
            raw = schedule_by_day[day_num]
            is_day_off = bool(raw.get("is_day_off", False))
            normalized.append(
                {
                    "day": day_num,
                    "day_name": DAY_NAMES[day_num],
                    "is_day_off": is_day_off,
                    "open_time": None if is_day_off else (raw.get("open_time") or "08:00"),
                    "close_time": None if is_day_off else (raw.get("close_time") or "22:00"),
                }
            )
        else:
            normalized.append(
                {
                    "day": day_num,
                    "day_name": DAY_NAMES[day_num],
                    "is_day_off": False,
                    "open_time": "08:00",
                    "close_time": "22:00",
                }
            )

    return normalized


def format_schedule_summary(schedule: list[dict[str, Any]] | None) -> str:
    normalized = normalize_schedule(schedule)

    # Check if all days are identical
    first = normalized[0]
    all_same = all(
        item["is_day_off"] == first["is_day_off"]
        and item["open_time"] == first["open_time"]
        and item["close_time"] == first["close_time"]
        for item in normalized
    )
    if all_same:
        if first["is_day_off"]:
            return "Магазин временно закрыт"
        if first["open_time"] == "00:00" and first["close_time"] in ("24:00", "23:59"):
            return "Круглосуточно (24/7)"
        return f"Ежедневно {first['open_time']}–{first['close_time']}"

    # Check Mon-Fri and Sat-Sun grouping
    mon_fri = normalized[0:5]
    sat_sun = normalized[5:7]

    mon_fri_same = all(
        item["is_day_off"] == mon_fri[0]["is_day_off"]
        and item["open_time"] == mon_fri[0]["open_time"]
        and item["close_time"] == mon_fri[0]["close_time"]
        for item in mon_fri
    )
    sat_sun_same = all(
        item["is_day_off"] == sat_sun[0]["is_day_off"]
        and item["open_time"] == sat_sun[0]["open_time"]
        and item["close_time"] == sat_sun[0]["close_time"]
        for item in sat_sun
    )

    if mon_fri_same and sat_sun_same:
        mf_text = (
            "выходной"
            if mon_fri[0]["is_day_off"]
            else f"{mon_fri[0]['open_time']}–{mon_fri[0]['close_time']}"
        )
        ss_text = (
            "выходной"
            if sat_sun[0]["is_day_off"]
            else f"{sat_sun[0]['open_time']}–{sat_sun[0]['close_time']}"
        )
        return f"Пн–Пт {mf_text}, Сб–Вс {ss_text}"

    # Group consecutive days with same schedule
    groups: list[tuple[list[int], dict[str, Any]]] = []
    current_days: list[int] = []
    current_key: tuple[bool, str | None, str | None] | None = None

    for item in normalized:
        key = (item["is_day_off"], item["open_time"], item["close_time"])
        if current_key is None or key == current_key:
            current_days.append(item["day"])
            current_key = key
        else:
            groups.append((current_days, normalized[current_days[0] - 1]))
            current_days = [item["day"]]
            current_key = key
    if current_days:
        groups.append((current_days, normalized[current_days[0] - 1]))

    parts: list[str] = []
    for days, sample in groups:
        if len(days) == 1:
            day_label = SHORT_DAY_NAMES[days[0]]
        else:
            day_label = f"{SHORT_DAY_NAMES[days[0]]}–{SHORT_DAY_NAMES[days[-1]]}"

        if sample["is_day_off"]:
            parts.append(f"{day_label} выходной")
        else:
            parts.append(f"{day_label} {sample['open_time']}–{sample['close_time']}")

    return ", ".join(parts)


def calculate_schedule_status(
    schedule: list[dict[str, Any]] | None,
    *,
    now: datetime | None = None,
    maintenance_mode: bool = False,
) -> tuple[bool, str]:
    if maintenance_mode:
        return False, "Магазин закрыт на техобслуживание"

    if now is None:
        now = datetime.now(settings.tz)

    normalized = normalize_schedule(schedule)
    current_weekday = now.isoweekday()  # 1 (Monday) to 7 (Sunday)

    today_item = next((item for item in normalized if item["day"] == current_weekday), None)
    if not today_item or today_item["is_day_off"]:
        return False, "Сегодня выходной"

    open_time_str = today_item.get("open_time")
    close_time_str = today_item.get("close_time")

    if not open_time_str or not close_time_str:
        return True, "Открыто"

    try:
        open_parts = [int(p) for p in open_time_str.split(":")]
        close_parts = [int(p) for p in close_time_str.split(":")]
        open_t = time(open_parts[0], open_parts[1])

        # Handle 24:00 as 23:59:59
        if close_parts[0] >= 24:
            close_t = time(23, 59, 59)
        else:
            close_t = time(close_parts[0], close_parts[1])

        now_t = now.time()

        if open_t <= now_t < close_t:
            return True, f"Открыто до {close_time_str}"
        elif now_t < open_t:
            return False, f"Закрыто (откроется в {open_time_str})"
        else:
            return False, "Закрыто до завтра"
    except Exception:
        return True, "Открыто"
