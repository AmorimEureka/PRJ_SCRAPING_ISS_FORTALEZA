from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta


MONTHS_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

MONTHS_BY_NAME = {value.lower(): key for key, value in MONTHS_PT.items()}


@dataclass(frozen=True, order=True)
class MonthPeriod:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError("Mes invalido. Use um valor entre 1 e 12.")

    @property
    def mm_yyyy(self) -> str:
        return f"{self.month:02d}/{self.year}"

    @property
    def yyyymm(self) -> str:
        return f"{self.year}{self.month:02d}"

    @property
    def display(self) -> str:
        return f"{MONTHS_PT[self.month]}, {self.year}"

    @property
    def label(self) -> str:
        return self.mm_yyyy

    @property
    def first_day_br(self) -> str:
        return f"01/{self.month:02d}/{self.year}"

    @property
    def last_day_br(self) -> str:
        last_day = monthrange(self.year, self.month)[1]
        return f"{last_day:02d}/{self.month:02d}/{self.year}"

    @property
    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def last_day(self) -> date:
        return date(self.year, self.month, monthrange(self.year, self.month)[1])

    def query_end_day(self, today: date | None = None) -> date:
        today = today or date.today()
        return min(self.last_day, today)

    def query_end_day_br(self, today: date | None = None) -> str:
        end_day = self.query_end_day(today)
        return end_day.strftime("%d/%m/%Y")

    @property
    def start_month_year_br(self) -> str:
        return self.first_day.strftime("%m/%Y")

    @property
    def end_month_year_br(self) -> str:
        return self.query_end_day().strftime("%m/%Y")

    def next_month(self) -> "MonthPeriod":
        if self.month == 12:
            return MonthPeriod(self.year + 1, 1)
        return MonthPeriod(self.year, self.month + 1)


@dataclass(frozen=True, order=True)
class DateRangePeriod:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("Data final deve ser maior ou igual a data inicial.")

    @property
    def label(self) -> str:
        return f"{self.first_day_br} a {self.query_end_day_br()}"

    @property
    def mm_yyyy(self) -> str:
        return self.label

    @property
    def yyyymm(self) -> str:
        return f"{self.start:%Y%m%d}_{self.query_end_day():%Y%m%d}"

    @property
    def display(self) -> str:
        return self.label

    @property
    def first_day_br(self) -> str:
        return self.start.strftime("%d/%m/%Y")

    @property
    def last_day_br(self) -> str:
        return self.end.strftime("%d/%m/%Y")

    @property
    def first_day(self) -> date:
        return self.start

    @property
    def last_day(self) -> date:
        return self.end

    def query_end_day(self, today: date | None = None) -> date:
        today = today or date.today()
        return min(self.end, today)

    def query_end_day_br(self, today: date | None = None) -> str:
        return self.query_end_day(today).strftime("%d/%m/%Y")

    @property
    def start_month_year_br(self) -> str:
        return self.start.strftime("%m/%Y")

    @property
    def end_month_year_br(self) -> str:
        return self.query_end_day().strftime("%m/%Y")


def parse_month_period(value: str) -> MonthPeriod:
    raw = value.strip()

    match = re.fullmatch(r"(\d{1,2})/(\d{4})", raw)
    if match:
        return MonthPeriod(year=int(match.group(2)), month=int(match.group(1)))

    match = re.fullmatch(r"(\d{4})-(\d{1,2})", raw)
    if match:
        return MonthPeriod(year=int(match.group(1)), month=int(match.group(2)))

    match = re.fullmatch(r"([A-Za-zÀ-ÿ]+),?\s+(\d{4})", raw)
    if match:
        month = MONTHS_BY_NAME.get(match.group(1).lower())
        if month:
            return MonthPeriod(year=int(match.group(2)), month=month)

    raise ValueError(
        "Competencia invalida. Use formatos como 06/2026, 2026-06 ou Junho, 2026."
    )


def parse_date(value: str) -> date:
    raw = value.strip()

    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if match:
        return date(year=int(match.group(3)), month=int(match.group(2)), day=int(match.group(1)))

    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if match:
        return date(year=int(match.group(1)), month=int(match.group(2)), day=int(match.group(3)))

    raise ValueError("Data invalida. Use formatos como 01/06/2026 ou 2026-06-01.")


def looks_like_date(value: str) -> bool:
    raw = value.strip()
    return bool(
        re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", raw)
        or re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", raw)
    )


def iter_months(start: MonthPeriod, end: MonthPeriod):
    current = start
    while current <= end:
        yield current
        current = current.next_month()


def iter_date_windows(start: date, end: date, *, today: date | None = None):
    today = today or date.today()
    if start > today:
        return

    final_end = min(end, today)
    current = start
    while current <= final_end:
        month_end = date(current.year, current.month, monthrange(current.year, current.month)[1])
        max_31_days_end = current + timedelta(days=30)
        window_end = min(month_end, max_31_days_end, final_end)
        yield DateRangePeriod(current, window_end)
        current = window_end + timedelta(days=1)
