from __future__ import annotations

from dataclasses import dataclass

from mail_parser import ParsedMail


@dataclass
class RuleDecision:
    forced_importance: str | None = None
    matched_rule: str = ""


class RuleEngine:
    def __init__(self, whitelist: list[str], keywords: list[str]) -> None:
        self.whitelist = [item.lower() for item in whitelist if item]
        self.keywords = [item.lower() for item in keywords if item]

    def evaluate(self, mail: ParsedMail) -> RuleDecision:
        sender = mail.sender_address.lower()
        haystack = f"{mail.subject}\n{mail.body_text}".lower()
        for entry in self.whitelist:
            if entry and entry in sender:
                return RuleDecision(forced_importance="high", matched_rule=f"whitelist:{entry}")
        for keyword in self.keywords:
            if keyword and keyword in haystack:
                return RuleDecision(forced_importance="high", matched_rule=f"keyword:{keyword}")
        return RuleDecision()
