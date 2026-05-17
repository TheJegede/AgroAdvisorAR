"""
AgroAdvisor AR load test.

Local run:
  TEST_EMAIL=... TEST_PASSWORD=... locust -f tests/locustfile.py \
    --host=http://localhost:8000 --users 50 --spawn-rate 5 \
    --run-time 3m --headless --html docs/security/locust-local.html

Prod run (after Railway deploy):
  TEST_EMAIL=... TEST_PASSWORD=... locust -f tests/locustfile.py \
    --host=https://<railway-url> --users 50 --spawn-rate 5 \
    --run-time 3m --headless --html docs/security/locust-prod.html
"""
import os
import re
from locust import HttpUser, task, between


class AgroAdvisorUser(HttpUser):
    wait_time = between(1, 3)
    _token: str | None = None
    _session_id: str | None = None
    _last_message_id: str | None = None

    def on_start(self):
        email = os.environ.get("TEST_EMAIL", "")
        password = os.environ.get("TEST_PASSWORD", "")
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code == 200:
            self._token = resp.json().get("access_token")

        if self._token:
            sess = self.client.post(
                "/api/v1/sessions",
                json={"preview": "load test session"},
                headers=self._auth(),
            )
            if sess.status_code == 200:
                self._session_id = sess.json().get("id")

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    @task(6)
    def query(self):
        if not self._token:
            return
        payload = {
            "message": "What are the recommended herbicides for rice in Arkansas?",
            "session_history": [],
        }
        if self._session_id:
            payload["session_id"] = self._session_id

        with self.client.post(
            "/api/v1/query",
            json=payload,
            headers=self._auth(),
            stream=True,
            catch_response=True,
            name="/api/v1/query",
        ) as resp:
            content = b""
            try:
                for chunk in resp.iter_content(chunk_size=4096):
                    content += chunk
            except Exception:
                pass
            match = re.search(rb'"message_id":\s*"([^"]+)"', content)
            if match:
                self._last_message_id = match.group(1).decode()
            resp.success()

    @task(2)
    def list_sessions(self):
        if not self._token:
            return
        self.client.get("/api/v1/sessions", headers=self._auth(), name="/api/v1/sessions")

    @task(1)
    def get_profile(self):
        if not self._token:
            return
        self.client.get("/api/v1/profile", headers=self._auth(), name="/api/v1/profile")

    @task(1)
    def submit_feedback(self):
        if not self._token or not self._last_message_id:
            return
        self.client.post(
            "/api/v1/feedback",
            json={"message_id": self._last_message_id, "rating": 1},
            headers=self._auth(),
            name="/api/v1/feedback",
        )
