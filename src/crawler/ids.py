from datetime import datetime


def generate_ids(start_month: str, start_id: int, end_month: str, end_id: int) -> list[str]:
    month = datetime.strptime(start_month, '%Y-%m')
    if start_month != end_month:
        raise ValueError('Only same-month ranges are supported')
    if not 1 <= start_id <= end_id <= 99999:
        raise ValueError('Invalid inclusive ID range')
    return [f'{month:%y%m}.{i:05d}' for i in range(start_id, end_id + 1)]
