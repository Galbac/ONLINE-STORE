from datetime import datetime, time
from zoneinfo import ZoneInfo

from source.utils.schedule import (
    calculate_schedule_status,
    format_schedule_summary,
    get_default_schedule,
    normalize_schedule,
)

TZ = ZoneInfo("Europe/Moscow")


def test_get_default_schedule():
    schedule = get_default_schedule()
    assert len(schedule) == 7
    for i, item in enumerate(schedule, start=1):
        assert item["day"] == i
        assert item["is_day_off"] is False
        assert item["open_time"] == "08:00"
        assert item["close_time"] == "22:00"


def test_format_schedule_summary_daily():
    schedule = get_default_schedule()
    summary = format_schedule_summary(schedule)
    assert summary == "Ежедневно 08:00–22:00"


def test_format_schedule_summary_24_7():
    schedule = [
        {"day": i, "is_day_off": False, "open_time": "00:00", "close_time": "24:00"}
        for i in range(1, 8)
    ]
    summary = format_schedule_summary(schedule)
    assert summary == "Круглосуточно (24/7)"


def test_format_schedule_summary_weekdays_and_weekends():
    schedule = []
    for i in range(1, 6):
        schedule.append({"day": i, "is_day_off": False, "open_time": "08:00", "close_time": "22:00"})
    for i in range(6, 8):
        schedule.append({"day": i, "is_day_off": False, "open_time": "09:00", "close_time": "20:00"})

    summary = format_schedule_summary(schedule)
    assert summary == "Пн–Пт 08:00–22:00, Сб–Вс 09:00–20:00"


def test_format_schedule_summary_with_day_off():
    schedule = []
    for i in range(1, 7):
        schedule.append({"day": i, "is_day_off": False, "open_time": "08:00", "close_time": "22:00"})
    schedule.append({"day": 7, "is_day_off": True, "open_time": None, "close_time": None})

    summary = format_schedule_summary(schedule)
    assert "Вс выходной" in summary


def test_calculate_schedule_status_maintenance():
    is_open, text = calculate_schedule_status([], maintenance_mode=True)
    assert is_open is False
    assert "техобслуживание" in text


def test_calculate_schedule_status_open():
    # Wednesday 14:30
    wednesday_dt = datetime(2026, 9, 23, 14, 30, tzinfo=TZ)
    assert wednesday_dt.isoweekday() == 3

    schedule = get_default_schedule()
    is_open, text = calculate_schedule_status(schedule, now=wednesday_dt)
    assert is_open is True
    assert text == "Открыто до 22:00"


def test_calculate_schedule_status_before_open():
    # Wednesday 07:15
    wednesday_dt = datetime(2026, 9, 23, 7, 15, tzinfo=TZ)
    schedule = get_default_schedule()
    is_open, text = calculate_schedule_status(schedule, now=wednesday_dt)
    assert is_open is False
    assert text == "Закрыто (откроется в 08:00)"


def test_calculate_schedule_status_after_close():
    # Wednesday 23:15
    wednesday_dt = datetime(2026, 9, 23, 23, 15, tzinfo=TZ)
    schedule = get_default_schedule()
    is_open, text = calculate_schedule_status(schedule, now=wednesday_dt)
    assert is_open is False
    assert text == "Закрыто до завтра"


def test_calculate_schedule_status_day_off():
    # Sunday (day 7)
    sunday_dt = datetime(2026, 9, 27, 14, 0, tzinfo=TZ)
    assert sunday_dt.isoweekday() == 7

    schedule = [
        {"day": i, "is_day_off": False, "open_time": "08:00", "close_time": "22:00"}
        for i in range(1, 7)
    ]
    schedule.append({"day": 7, "is_day_off": True})

    is_open, text = calculate_schedule_status(schedule, now=sunday_dt)
    assert is_open is False
    assert text == "Сегодня выходной"
