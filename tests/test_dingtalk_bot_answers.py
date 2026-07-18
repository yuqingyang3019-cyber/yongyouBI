from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.dingtalk_bot.receivable_answers import answer_receivable_question


class DingTalkBotAnswersTest(unittest.TestCase):
    @patch("backend.dingtalk_bot.receivable_answers.get_receivable_store")
    @patch("backend.dingtalk_bot.receivable_answers.load_receivable_snapshot")
    def test_answers_receivable_question_from_cached_data(self, snapshot_mock, store_mock) -> None:
        snapshot_mock.return_value = (
            [{"invoiceId": "i1"}],
            {"overdue": {"count": 2, "amount": 1234.5}, "upcoming": {"count": 1, "amount": 100}},
            {},
        )
        store_mock.return_value.count_all_collections.return_value = 3

        answer = answer_receivable_question("当前逾期金额是多少？")

        self.assertIn("已逾期：2 笔，¥1,234.50", answer)
        self.assertIn("缓存收款：3 笔", answer)

    def test_returns_help_for_non_receivable_question(self) -> None:
        self.assertIn("应收概览", answer_receivable_question("你好"))


if __name__ == "__main__":
    unittest.main()
