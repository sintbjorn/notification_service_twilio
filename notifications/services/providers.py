import smtplib
from email.message import EmailMessage

import requests


class EmailProvider:
    def __init__(self, host, port, user, password, use_tls=True, sender=None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls
        self.sender = sender or user or "no-reply@example.com"

    def send(self, to_email: str, subject: str, body: str):
        if not to_email:
            raise ValueError("Recipient email is empty")
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to_email
        msg["Subject"] = subject or "(no subject)"
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=15) as s:
            if self.use_tls:
                try:
                    s.starttls()
                except smtplib.SMTPException:
                    pass
            if self.user and self.password:
                s.login(self.user, self.password)
            s.send_message(msg)


class SmsProvider:
    def __init__(self, account_sid, auth_token, from_number):
        self.sid = account_sid
        self.token = auth_token
        self.from_number = from_number

    def send(self, to_phone: str, body: str):
        if not to_phone:
            raise ValueError("Recipient phone is empty")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"
        data = {
            "From": self.from_number,
            "To": to_phone,
            "Body": body,
        }
        resp = requests.post(url, data=data, auth=(self.sid, self.token), timeout=15)
        if not resp.ok:
            try:
                info = resp.json()
                msg = info.get("message") or resp.text
            except Exception as exc:
                msg = resp.text
                raise RuntimeError(f"Twilio error: HTTP {resp.status_code} - {msg}") from exc
            raise RuntimeError(f"Twilio error: HTTP {resp.status_code} - {msg}")


class TelegramProvider:
    def __init__(self, bot_token):
        self.bot_token = bot_token

    def send(self, chat_id: str, body: str):
        if not chat_id:
            raise ValueError("Recipient chat_id is empty")
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": body,
            },
            timeout=10,
        )
        if not resp.ok:
            try:
                info = resp.json()
                msg = info.get("description") or resp.text
            except Exception as exc:
                msg = resp.text
                raise RuntimeError(f"Telegram error: {msg}") from exc
            raise RuntimeError(f"Telegram error: {msg}")
