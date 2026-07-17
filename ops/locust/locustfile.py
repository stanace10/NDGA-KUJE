import csv
import os
import random
from pathlib import Path

from locust import HttpUser, between, task


def load_candidates():
    path = os.getenv("LOCUST_USERS_FILE", "").strip()
    if not path:
        return []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


CANDIDATES = load_candidates()


class CBTStudent(HttpUser):
    wait_time = between(0.8, 2.2)

    def on_start(self):
        if not CANDIDATES:
            raise RuntimeError("Set LOCUST_USERS_FILE to a CSV with username,password,exam_id rows.")
        self.candidate = CANDIDATES.pop(0) if CANDIDATES else random.choice(load_candidates())
        login = self.client.get("/auth/login/", name="01 login page")
        token = login.cookies.get("csrftoken", "")
        response = self.client.post(
            "/auth/login/",
            data={
                "username": self.candidate["username"],
                "password": self.candidate["password"],
                "csrfmiddlewaretoken": token,
            },
            headers={"Referer": f"{self.host}/auth/login/"},
            name="02 login submit",
        )
        exam_id = self.candidate["exam_id"]
        start = self.client.post(
            f"/cbt/exams/{exam_id}/start/",
            data={"csrfmiddlewaretoken": self.client.cookies.get("csrftoken", "")},
            headers={"Referer": f"{self.host}/cbt/exams/available/"},
            name="03 start exam",
        )
        self.attempt_url = start.url if "/attempts/" in start.url else ""
        if self.attempt_url:
            self.client.get(self.attempt_url, name="04 question page")

    @task(8)
    def navigate_question(self):
        if not self.attempt_url:
            return
        question = random.randint(1, int(os.getenv("LOCUST_QUESTION_COUNT", "20")))
        self.client.get(f"{self.attempt_url}?q={question}", name="05 fetch question")

    @task(12)
    def save_answer(self):
        if not self.attempt_url:
            return
        question = random.randint(1, int(os.getenv("LOCUST_QUESTION_COUNT", "20")))
        option_id = os.getenv(f"LOCUST_OPTION_ID_{question}", "")
        if not option_id:
            return
        self.client.post(
            self.attempt_url,
            data={
                "action": "save_stay",
                "q": question,
                "selected_options": option_id,
                "csrfmiddlewaretoken": self.client.cookies.get("csrftoken", ""),
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": self.attempt_url},
            name="06 answer save",
        )

    @task(1)
    def heartbeat(self):
        if not self.attempt_url:
            return
        attempt_id = self.attempt_url.rstrip("/").split("/")[-2]
        self.client.post(
            f"/cbt/attempts/{attempt_id}/heartbeat/",
            data={"tab_token": f"locust-{self.candidate['username']}"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            name="07 heartbeat",
        )
