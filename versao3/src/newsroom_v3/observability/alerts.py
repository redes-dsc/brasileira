def should_alert_low_throughput(published_per_hour: int) -> bool:
    return published_per_hour < 20


def should_alert_no_image_rate(no_image_rate: float) -> bool:
    return no_image_rate > 0.05
