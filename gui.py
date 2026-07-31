"""Re:Zero 双子系统 —— PySide6(Qt) 图形界面聊天窗口。

双击运行或启动后弹出窗口，像 QQ/微信一样聊天。
自动保存聊天记录和好感度到 data/memory.json，重启后记忆恢复。
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 确保项目根目录在路径中
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.config import load_env

load_env()

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QColor, QTextCursor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QFrame,
    QScrollArea,
    QMessageBox,
    QSizePolicy,
)

from local import ReZeroTwinSystem
from shared.state import StoryArc
from shared.memory_store import MemoryStore


_LOG_PATH = os.path.join(_PROJECT_ROOT, "data", "gui.log")


def _log(msg: str) -> None:
    """写日志到文件，便于无控制台时排查问题。"""
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


_log("=== GUI 启动 ===")


class BubbleLabel(QLabel):
    """聊天气泡标签。"""

    def __init__(self, text: str, is_user: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setFont(QFont("Microsoft YaHei", 11))
        self.setContentsMargins(12, 8, 12, 8)

        if is_user:
            bg = "#95ec69"
            fg = "#1a1a1a"
        else:
            bg = "#ffffff"
            fg = "#1a1a1a"

        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border-radius: 10px;
                padding: 8px 12px;
            }}
        """
        )
        self.setText(text)


class ChatMessageWidget(QWidget):
    """一条聊天消息：头像 + 气泡。"""

    def __init__(self, sender: str, text: str, is_user: bool = False, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        avatar = QLabel(sender[:2])
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(36, 36)
        avatar.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        avatar.setStyleSheet(
            f"""
            QLabel {{
                background-color: {'#07c160' if is_user else '#ff6b9d'};
                color: white;
                border-radius: 18px;
            }}
        """
        )

        bubble = BubbleLabel(text, is_user=is_user)
        bubble.setMaximumWidth(520)

        if is_user:
            layout.addStretch()
            layout.addWidget(bubble)
            layout.addWidget(avatar)
        else:
            layout.addWidget(avatar)
            layout.addWidget(bubble)
            layout.addStretch()


class TwinChatApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        _log("TwinChatApp.__init__ 开始")
        try:
            self.setWindowTitle("Re:Zero 双子系统")
            self.setMinimumSize(880, 640)
            self.resize(960, 720)

            self.store = MemoryStore(_PROJECT_ROOT)
            self.mem = self.store.load()
            _log(f"记忆加载完成: mode={self.mem.get('mode')}, arc={self.mem.get('arc')}")

            self.mode = self.mem.get("mode", "llm")
            self.chat_history: list[dict] = list(self.mem.get("chat_history", []))

            self._setup_ui()
            self._apply_theme()
            self._load_history()

            # UI 准备好后再创建 bot（失败时可以弹窗）
            self.bot = self._create_bot()
            self.status_label.setText(f"模式: {self.mode.upper()} | 篇章: {self._arc_name()}")
            self._append_message("系统", f"ReZero 双子系统启动成功。当前模式：{self.mode.upper()}")
            _log("TwinChatApp.__init__ 完成")
        except Exception as e:
            _log(f"TwinChatApp.__init__ 异常: {e}\n{traceback.format_exc()}")
            raise

    def _create_bot(self):
        _log(f"_create_bot 开始, mode={self.mode}")
        if self.mode == "llm":
            try:
                from llm import ReZeroLLMBridge

                api_key = os.getenv("DEEPSEEK_API_KEY")
                _log(f"api_key 存在: {bool(api_key)}")
                bot = ReZeroLLMBridge(
                    api_key=api_key,
                    base_url="https://api.deepseek.com",
                    model_name="deepseek-chat",
                    arc=StoryArc(self.mem.get("arc", "mansion_era")),
                    max_history=8,
                )
                bot.engine.favor = self.mem.get("favor", 15)
                bot.engine.ram_favor = self.mem.get("ram_favor", 8)
                bot.engine.independence = self.mem.get("independence", 0.25)
                bot.engine.recovery = self.mem.get("recovery", 1.0)
                _log("LLM bot 创建成功")
                return bot
            except Exception as e:
                _log(f"LLM bot 创建失败: {e}\n{traceback.format_exc()}")
                QMessageBox.warning(
                    self,
                    "LLM 模式不可用",
                    f"{e}\n\n请将包含 DEEPSEEK_API_KEY 的 .env 放到程序同目录。\n"
                    "本次启动将使用本地模板模式。",
                )
                self.mode = "local"

        bot = ReZeroTwinSystem()
        bot.rem.engine.favor = self.mem.get("favor", 15)
        bot.rem.engine.ram_favor = self.mem.get("ram_favor", 8)
        bot.rem.engine.independence = self.mem.get("independence", 0.25)
        bot.rem.engine.recovery = self.mem.get("recovery", 1.0)
        try:
            bot.set_arc(StoryArc(self.mem.get("arc", "mansion_era")))
        except ValueError:
            bot.set_arc(StoryArc.MANSION_ERA)
        _log("本地 bot 创建成功")
        return bot

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 顶部标题栏
        header = QFrame()
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("Re:Zero 双子系统")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        header_layout.addWidget(title)

        header_layout.addStretch()

        self.status_label = QLabel("正在初始化...")
        self.status_label.setFont(QFont("Microsoft YaHei", 10))
        header_layout.addWidget(self.status_label)

        main_layout.addWidget(header)

        # 聊天区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.addStretch()

        self.scroll.setWidget(self.chat_container)
        main_layout.addWidget(self.scroll, 1)

        # 输入区域
        input_frame = QFrame()
        input_frame.setFixedHeight(120)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(16, 10, 16, 16)
        input_layout.setSpacing(10)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText("输入消息，按 Enter 发送，Shift+Enter 换行...")
        self.input_box.setFont(QFont("Microsoft YaHei", 11))
        self.input_box.setFixedHeight(80)
        self.input_box.installEventFilter(self)
        input_row.addWidget(self.input_box, 1)

        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedSize(80, 80)
        self.send_btn.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._send_message)
        input_row.addWidget(self.send_btn)

        input_layout.addLayout(input_row)
        main_layout.addWidget(input_frame)

        # 底部状态栏
        footer = QFrame()
        footer.setFixedHeight(30)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 0, 16, 0)

        self.footer_label = QLabel("就绪")
        self.footer_label.setFont(QFont("Microsoft YaHei", 9))
        footer_layout.addWidget(self.footer_label)
        footer_layout.addStretch()

        main_layout.addWidget(footer)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f5f5f5;
            }
            QFrame {
                background-color: #ffffff;
                border: none;
            }
            QTextEdit {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 8px;
                background-color: #ffffff;
            }
            QPushButton {
                background-color: #07c160;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #06ad56;
            }
            QPushButton:pressed {
                background-color: #059a4c;
            }
            QPushButton:disabled {
                background-color: #a0a0a0;
            }
            QScrollArea {
                border: none;
                background-color: #f5f5f5;
            }
        """
        )

    def _arc_name(self) -> str:
        try:
            return self.bot.engine.arc.value
        except AttributeError:
            return self.bot.rem.engine.arc.value

    def _load_history(self) -> None:
        _log(f"_load_history: {len(self.chat_history)} 条")
        for item in self.chat_history[-20:]:
            sender = item.get("sender", "未知")
            text = item.get("text", "")
            self._append_message(sender, text, is_user=(sender == "你"), save=False)

    def _append_message(self, sender: str, text: str, is_user: bool = False, save: bool = True) -> None:
        msg = ChatMessageWidget(sender, text, is_user=is_user)
        insert_index = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(insert_index, msg)
        if save:
            self.chat_history.append({"sender": sender, "text": text})
            # 限制内存中数量
            if len(self.chat_history) > 200:
                self.chat_history = self.chat_history[-200:]
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        vsb = self.scroll.verticalScrollBar()
        vsb.setValue(vsb.maximum())

    def _send_message(self) -> None:
        text = self.input_box.toPlainText().strip()
        if not text:
            return

        _log(f"发送消息: {text[:30]}")
        self.input_box.clear()
        self._append_message("你", text, is_user=True)
        self.footer_label.setText("双子正在思考...")
        self.send_btn.setEnabled(False)

        QTimer.singleShot(100, lambda: self._get_reply(text))

    def _get_reply(self, text: str) -> None:
        try:
            if self.mode == "llm":
                reply = self.bot.chat(text)
            else:
                reply = self.bot.interact(text)
            _log(f"收到回复: {reply[:60]}")
        except Exception as e:
            reply = f"【系统】出错了：{e}"
            _log(f"获取回复异常: {e}\n{traceback.format_exc()}")

        self._append_message("双子", reply, is_user=False)
        self._save_state()
        self.footer_label.setText("就绪")
        self.send_btn.setEnabled(True)

    def _save_state(self) -> None:
        try:
            engine = self.bot.engine if self.mode == "llm" else self.bot.rem.engine
            data = self.store.load()
            data.update(
                {
                    "mode": self.mode,
                    "arc": engine.arc.value,
                    "favor": engine.favor,
                    "ram_favor": engine.ram_favor,
                    "independence": engine.independence,
                    "recovery": engine.recovery,
                    "chat_history": self.chat_history[-200:],
                }
            )
            self.store.save(data)
            _log("状态保存成功")
        except Exception as e:
            err = f"保存状态失败: {e}"
            self.footer_label.setText(err)
            _log(f"{err}\n{traceback.format_exc()}")

    def eventFilter(self, source, event) -> bool:
        from PySide6.QtCore import QEvent
        if source is self.input_box and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
                self._send_message()
                return True
        return super().eventFilter(source, event)

    def closeEvent(self, event) -> None:
        self._save_state()
        event.accept()


def main() -> None:
    try:
        app = QApplication(sys.argv)
        app.setFont(QFont("Microsoft YaHei", 10))
        window = TwinChatApp()
        window.show()
        _log("窗口 show 完成，进入事件循环")
        sys.exit(app.exec())
    except Exception as e:
        _log(f"main 异常: {e}\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    main()
