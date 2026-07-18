from __future__ import annotations

import logging

from backend.config import optional_env, require_env
from backend.dingtalk_bot.receivable_answers import answer_receivable_question

logger = logging.getLogger(__name__)


def _allowed_group_ids() -> set[str]:
    return {
        item.strip()
        for item in optional_env("DINGTALK_BOT_ALLOWED_GROUP_IDS").split(",")
        if item.strip()
    }


def _is_allowed_group(conversation_id: str | None) -> bool:
    allowed = _allowed_group_ids()
    return bool(conversation_id) and (not allowed or conversation_id in allowed)


def run() -> None:
    from dingtalk_stream import ChatbotHandler, ChatbotMessage, Credential, DingTalkStreamClient
    from dingtalk_stream.frames import AckMessage

    class ReceivableBotHandler(ChatbotHandler):
        async def process(self, callback_message):
            message = ChatbotMessage.from_dict(callback_message.data)
            if not message.is_in_at_list or message.conversation_type != "2":
                return AckMessage.STATUS_OK, "ignored"
            if not _is_allowed_group(message.conversation_id):
                logger.warning("ignored message from unapproved group: %s", message.conversation_id)
                return AckMessage.STATUS_OK, "ignored"
            if message.message_type != "text" or not message.text:
                self.reply_text("请使用文字 @我提问应收数据。", message)
                return AckMessage.STATUS_OK, "unsupported message"

            question = message.text.content.strip()
            logger.info(
                "received receivable question: conversation=%s sender=%s length=%s",
                message.conversation_id,
                message.sender_staff_id,
                len(question),
            )
            self.reply_text(answer_receivable_question(question), message)
            return AckMessage.STATUS_OK, "ok"

    app_key = require_env("DINGTALK_APP_KEY")
    app_secret = require_env("DINGTALK_APP_SECRET")
    client = DingTalkStreamClient(Credential(app_key, app_secret))
    client.register_callback_handler(ChatbotMessage.TOPIC, ReceivableBotHandler())
    logger.info("starting DingTalk receivable bot")
    client.start_forever()


if __name__ == "__main__":
    logging.basicConfig(level=optional_env("DINGTALK_BOT_LOG_LEVEL", "INFO"))
    run()
