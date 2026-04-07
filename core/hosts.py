from django_hosts import host, patterns

host_patterns = patterns(
    "",
    host(r"", "core.urls", name="landing"),
    host(r"portal", "core.urls", name="portal"),
    host(r"student", "core.urls", name="student"),
    host(r"staff", "core.urls", name="staff"),
    host(r"it", "core.urls", name="it"),
    host(r"bursar", "core.urls", name="bursar"),
    host(r"vp", "core.urls", name="vp"),
    host(r"principal", "core.urls", name="principal"),
    host(r"cbt", "core.urls", name="cbt"),
    host(r"election", "core.urls", name="election"),
)
