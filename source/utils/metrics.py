import time
from collections import defaultdict
from fastapi import Request, Response


class MetricsCollector:
    def __init__(self):
        self.start_time = time.time()
        self.request_counts = defaultdict(int)
        self.request_latencies = defaultdict(float)

    def record_request(self, method: str, endpoint: str, status_code: int, duration: float):
        # Normalize endpoint to reduce cardinality
        key = (method, endpoint, str(status_code))
        self.request_counts[key] += 1
        self.request_latencies[(method, endpoint)] += duration

    def export_prometheus(self) -> str:
        lines = []
        lines.append("# HELP http_requests_total Total number of HTTP requests processed.")
        lines.append("# TYPE http_requests_total counter")
        for (method, endpoint, status_code), count in sorted(self.request_counts.items()):
            lines.append(
                f'http_requests_total{{method="{method}",endpoint="{endpoint}",status="{status_code}"}} {count}'
            )

        lines.append("# HELP process_uptime_seconds Process uptime in seconds.")
        lines.append("# TYPE process_uptime_seconds gauge")
        lines.append(f"process_uptime_seconds {int(time.time() - self.start_time)}")

        lines.append("# HELP grocerystore_app_info Application metadata.")
        lines.append("# TYPE grocerystore_app_info gauge")
        lines.append('grocerystore_app_info{version="0.1.0",env="production"} 1')

        return "\n".join(lines) + "\n"


metrics_collector = MetricsCollector()
